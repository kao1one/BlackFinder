# BlackFinder

Localizador de produtos de loja, offline, para Android (Termux + Chrome).
Cole os códigos de um pedido e veja a localização de cada produto, agrupada por local.

**O catálogo (banco de dados) não faz parte deste repositório.** Ele fica só no celular,
dentro do Chrome, e é importado pelo próprio app.

## Arquivos
- `localizador.html`: o app inteiro (HTML + JS), com busca em memória e catálogo no IndexedDB.
- `servir.py`: servidor local em `localhost:8765` (só biblioteca padrão). O app instalado funciona sem ele.
- `verificar.py`: confere o ambiente (Python, módulos, arquivos, porta).
- `converter.py`: converte uma lista em texto (um local por bloco, linhas com códigos) em CSV.
- `checar_repo.py`: confere se nenhum dado do catálogo vai parar no repositório.

## Uso
```
python verificar.py
python servir.py
```
Abra `http://localhost:8765` no Chrome, importe o catálogo em **Catálogo** e instale o app pelo menu do Chrome.

## Formato do catálogo (CSV com `;`)
```
codigo;local;descricao
AB-12345;Prateleira 1;
AB-12346;Prateleira 2;Exemplo
```
