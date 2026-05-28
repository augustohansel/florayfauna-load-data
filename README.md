# Smartcampus Flora e Funga - Ingestão de Dados ⚙️

Este repositório contém o script de carga e processamento de dados responsável por extrair, transformar e indexar o catálogo de espécies biológicas no **Elasticsearch**. Ele funciona como a engrenagem de ETL (Extract, Transform, Load) que popula o motor de busca utilizado pelo aplicativo principal.

## 🔄 Fluxo de Funcionamento

1. **Extração:** Leitura dos dados brutos de fontes taxonômicas (como arquivos CSV, JSON ou planilhas de referência botânica).
2. **Transformação:** Tratamento, limpeza e normalização dos dados. Nesta etapa, a estrutura hierárquica das espécies (Reino, Família, Gênero, Espécie e nomes populares) é mapeada e padronizada para garantir a consistência dos índices.
3. **Carga:** Indexação em lote (*Bulk Index*) para o Elasticsearch, preparando os documentos com as configurações ideais de busca e autocomplete.

## 🚀 Tecnologias Utilizadas

* **Ambiente de Execução:** [Python](https://python.org/)
* **Cliente Elasticsearch:** Integração oficial com a API do Elasticsearch para manipulação de índices e envio de documentos em lote.
* **Módulos de Parsing:** Bibliotecas para leitura e processamento eficiente de arquivos pesados de dados.
