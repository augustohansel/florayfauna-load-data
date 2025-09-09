import csv
import json
import requests

# Nomes dos arquivos
INPUT_TAXON_FILE = 'taxon.txt'
INPUT_VERNACULAR_FILE = 'vernacularname.txt'
INPUT_DISTRIBUTION_FILE = 'distribution.txt'
OUTPUT_FILE = 'taxons_for_elastic.json'
ERROR_LOG_FILE = 'errors.log'

# URL do Elasticsearch
ELASTICSEARCH_URL = "https://localhost:9200"
# Autenticação
ES_USERNAME = "elastic"
ES_PASSWORD = "9FLiUc0Pynz4fiVRtWng"


def carregar_taxa(arquivo_taxon):
    """Carrega todos os dados do arquivo de táxons em um dicionário."""
    taxons_por_id = {}
    with open(arquivo_taxon, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for linha in reader:
            taxons_por_id[linha['id']] = linha
    return taxons_por_id


def carregar_nomes_vernaculares(arquivo_vernacular):
    """Carrega nomes vernaculares agrupados por ID de táxon."""
    nomes_por_id = {}
    with open(arquivo_vernacular, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for linha in reader:
            taxon_id = linha['id']
            if taxon_id not in nomes_por_id:
                nomes_por_id[taxon_id] = []
            nomes_por_id[taxon_id].append({
                "name": linha.get("vernacularName"),
                "language": linha.get("language"),
                "locality": linha.get("locality")
            })
    return nomes_por_id


def carregar_distribuicao(arquivo_distribuicao):
    """Carrega dados de distribuição agrupados por ID de táxon."""
    distribuicao_por_id = {}
    with open(arquivo_distribuicao, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for linha in reader:
            taxon_id = linha['id']
            if taxon_id not in distribuicao_por_id:
                distribuicao_por_id[taxon_id] = []

            try:
                remarks = json.loads(linha.get('occurrenceRemarks', '{}'))
            except json.JSONDecodeError:
                remarks = {}

            distribuicao_por_id[taxon_id].append({
                "locationID": linha.get("locationID"),
                "countryCode": linha.get("countryCode"),
                "establishmentMeans": linha.get("establishmentMeans"),
                "occurrenceRemarks": remarks
            })
    return distribuicao_por_id


def gerar_json_para_elastic(taxons_por_id, nomes_por_id, distribuicao_por_id, caminho_saida, log_erros):
    """Gera o arquivo NDJSON para o Bulk API do Elasticsearch."""
    data = []
    sinonimos_por_aceito = {}

    hierarchy_levels = ['kingdom', 'phylum', 'class', 'order', 'family', 'genus',
                        'specificEpithet', 'infraspecificEpithet']

    with open(log_erros, 'w', encoding='utf-8') as logfile:
        for doc in taxons_por_id.values():
            try:
                elastic_doc = {
                    "id": doc.get("id"),
                    "taxonID": doc.get("taxonID"),
                    "scientificName": doc.get("scientificName"),
                    "taxonRank": doc.get("taxonRank"),
                    "acceptedNameUsage": doc.get("acceptedNameUsage"),
                    "acceptedNameUsageID": doc.get("acceptedNameUsageID"),
                    "taxonomicStatus": doc.get("taxonomicStatus"),
                    "nomenclaturalStatus": doc.get("nomenclaturalStatus"),
                    "higherClassification": {},
                    "metadata": {
                        "modified": doc.get("modified"),
                        "bibliographicCitation": doc.get("bibliographicCitation"),
                        "references": doc.get("references")
                    },
                    "parent": {},
                    "locations": []
                }

                # Higher classification
                for level in hierarchy_levels:
                    if doc.get(level) and doc.get(level) not in ('NA', ''):
                        elastic_doc["higherClassification"][level] = doc.get(level)

                # Parent
                parent_id = doc.get("parentNameUsageID")
                if parent_id and parent_id in taxons_por_id:
                    parent_doc = taxons_por_id[parent_id]
                    elastic_doc["parent"] = {
                        "id": parent_id,
                        "scientificName": parent_doc.get("scientificName"),
                        "taxonRank": parent_doc.get("taxonRank")
                    }
                elif parent_id and doc.get("parentNameUsage"):
                    elastic_doc["parent"] = {
                        "id": parent_id,
                        "scientificName": doc.get("parentNameUsage"),
                        "taxonRank": "UNKNOWN"
                    }

                # Vernacular names
                taxon_id = elastic_doc["id"]
                if taxon_id in nomes_por_id:
                    elastic_doc["vernacularNames"] = nomes_por_id[taxon_id]

                # Distribution
                if taxon_id in distribuicao_por_id:
                    elastic_doc["distribution"] = distribuicao_por_id[taxon_id]

                # Synonyms
                if elastic_doc["taxonomicStatus"] == "SINONIMO":
                    accepted_id = elastic_doc["acceptedNameUsageID"]
                    if accepted_id not in sinonimos_por_aceito:
                        sinonimos_por_aceito[accepted_id] = []
                    sinonimos_por_aceito[accepted_id].append({
                        "id": elastic_doc["id"],
                        "scientificName": elastic_doc["scientificName"],
                        "taxonomicStatus": "SINONIMO"
                    })

                # Validação JSON
                json.dumps(elastic_doc, ensure_ascii=False)
                data.append(elastic_doc)

            except Exception as e:
                logfile.write(f"Erro ao processar o táxon com ID {doc.get('id')}: {e}\n")

    for doc in data:
        if doc["id"] in sinonimos_por_aceito:
            doc["sinonyms"] = sinonimos_por_aceito[doc["id"]]

    # Salva em formato NDJSON
    with open(caminho_saida, 'w', encoding='utf-8') as outfile:
        for doc in data:
            action = {"index": {"_index": "flora_funga_taxonomy", "_id": doc["id"]}}
            outfile.write(json.dumps(action) + '\n')
            outfile.write(json.dumps(doc, ensure_ascii=False) + '\n')
        outfile.write('\n')

    print(f"\nProcessamento concluído. O arquivo '{caminho_saida}' foi gerado.")
    print(f"Erros de processamento foram registrados no arquivo '{log_erros}'.")


def carregar_dados_em_lotes(arquivo_entrada, batch_size=5000):
    """
    Envia o arquivo NDJSON para o Elasticsearch em blocos de batch_size documentos.
    Cada documento ocupa 2 linhas no NDJSON (action + doc).
    """
    print("Iniciando a carga de dados...")
    headers = {"Content-Type": "application/x-ndjson"}
    auth = (ES_USERNAME, ES_PASSWORD)

    try:
        buffer = []
        count = 0

        with open(arquivo_entrada, 'r', encoding='utf-8') as f:
            for line in f:
                buffer.append(line)
                if len(buffer) >= batch_size * 2:  # 2 linhas por doc
                    payload = "".join(buffer)
                    response = requests.post(
                        f"{ELASTICSEARCH_URL}/_bulk",
                        data=payload.encode("utf-8"),
                        headers=headers,
                        auth=auth,
                        verify=False,
                        timeout=60
                    )
                    print("Status:", response.status_code)
                    if response.status_code != 200:
                        print("Erro no envio:", response.text[:500])
                    buffer = []
                    count += batch_size
                    print(f"→ {count} documentos enviados")

            # envia o resto
            if buffer:
                payload = "".join(buffer)
                response = requests.post(
                    f"{ELASTICSEARCH_URL}/_bulk",
                    data=payload.encode("utf-8"),
                    headers=headers,
                    auth=auth,
                    verify=False,
                    timeout=60
                )
                print("Status:", response.status_code)
                if response.status_code != 200:
                    print("Erro no envio:", response.text[:500])
                print(f"→ Total enviado: {count + len(buffer)//2} documentos")

    except Exception as e:
        print(f"Erro inesperado: {e}")
        return False

    print("\nCarga de dados concluída!")
    return True


# --- Execução do Script ---
if __name__ == "__main__":
    print("Passo 1: Gerando o arquivo JSON para o Elasticsearch...")
    taxa_mapa = carregar_taxa(INPUT_TAXON_FILE)
    nomes_vernaculares_mapa = carregar_nomes_vernaculares(INPUT_VERNACULAR_FILE)
    distribuicao_mapa = carregar_distribuicao(INPUT_DISTRIBUTION_FILE)
    gerar_json_para_elastic(taxa_mapa, nomes_vernaculares_mapa, distribuicao_mapa, OUTPUT_FILE, ERROR_LOG_FILE)

    print("\nPasso 2: Enviando o arquivo JSON para o Elasticsearch...")
    carregar_dados_em_lotes(OUTPUT_FILE, batch_size=5000)
