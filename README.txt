
# BBH — Lavanderia PRO (Flask + SQLite)

## Como rodar
1) Crie um ambiente virtual (opcional) e instale dependências:
```
pip install -r requirements.txt
```
2) Rode o servidor:
```
python app.py
```
3) Acesse no navegador: http://localhost:5000

## O que já faz
- Itens pré-cadastrados do enxoval BBH.
- Cadastro de itens (ativar/inativar).
- Movimentações: **Entrada, Saída, Envio, Retorno, Perda**.
- Estoque atual com separação **No Hotel** x **Em Lavanderia** e **Total**.
- Dashboard com **Envios x Retornos (7 dias)**.
- **Romaneio por dia** (Envio/Retorno) e **download CSV**.
- **Exportar inventário** em CSV.

## Observações
- O banco `lavanderia.db` é criado automaticamente na primeira execução.
- Para gerar executável no Windows: `pip install pyinstaller` e depois `pyinstaller -F app.py`.

Novidades:
- Exportar Romaneio em PDF (ReportLab).
- Movimentação em lote (vários itens na mesma operação).
- Visual remodelado + crédito 'Criado por André Vinicius'.
