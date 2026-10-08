#!/data/data/com.termux/files/usr/bin/bash
set -e

PROJETO="$HOME/blackfinder"
DESTINO="$PROJETO/dados"
NOME_FINAL="catalogo.csv"

POSSIVEIS=(
  "$HOME/storage/downloads/catalogo_completo_106_itens.csv"
  "$HOME/storage/shared/Download/catalogo_completo_106_itens.csv"
  "/sdcard/Download/catalogo_completo_106_itens.csv"
  "/storage/emulated/0/Download/catalogo_completo_106_itens.csv"
)

echo "→ Verificando projeto em: $PROJETO"

if [ ! -d "$PROJETO" ]; then
  echo "ERRO: Pasta do projeto não encontrada: $PROJETO"
  exit 1
fi

mkdir -p "$DESTINO"
echo "→ Pasta dados pronta: $DESTINO"

ARQUIVO=""
for caminho in "${POSSIVEIS[@]}"; do
  if [ -f "$caminho" ]; then
    ARQUIVO="$caminho"
    break
  fi
done

if [ -z "$ARQUIVO" ]; then
  echo "ERRO: Não encontrei o arquivo catalogo_completo_106_itens.csv na pasta Downloads."
  echo "Verifique se o arquivo está realmente em Downloads."
  exit 1
fi

echo "→ Arquivo encontrado: $ARQUIVO"
mv "$ARQUIVO" "$DESTINO/$NOME_FINAL"

echo "→ Arquivo movido com sucesso!"
echo "→ Local final: $DESTINO/$NOME_FINAL"
echo ""
echo "Conteúdo da pasta dados:"
ls -la "$DESTINO"
echo ""
echo "Tudo pronto."
