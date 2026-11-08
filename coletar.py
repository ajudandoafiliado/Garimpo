"""Garimpo: coleta os produtos mais vendidos da Shopee pela Open API de Afiliados
e grava data/produtos.json. Roda sozinho no GitHub Actions."""
import os, sys, json, time, hashlib, datetime, requests

ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"
APP_ID = os.environ["SHOPEE_APP_ID"]
SECRET = os.environ["SHOPEE_APP_SECRET"]
SORT_VENDAS = 2          # 2 = mais vendidos
POR_PALAVRA = 8          # produtos guardados por palavra-chave
TOTAL = 60               # tamanho final da lista

# categoria -> palavras-chave pesquisadas
PALAVRAS = {
    "Casa": ["lençol casal", "cortina blackout", "difusor aromatizador", "organizador", "luminária led", "decoração natal"],
    "Tecnologia": ["fone bluetooth", "carregador turbo", "smartwatch", "caixa de som bluetooth", "suporte celular", "drone"],
    "Beleza": ["escova secadora", "sérum facial", "protetor solar", "máscara capilar"],
    "Moda": ["tênis esportivo", "legging fitness", "bolsa feminina", "óculos de sol"],
    "Pet": ["tapete higiênico", "cama pet"],
    "Esporte": ["garrafa academia", "elástico treino"],
    "Infantil": ["brinquedo infantil"],
}

QUERY = """query { productOfferV2(keyword: %s, sortType: %d, page: 1, limit: %d) {
  nodes { itemId productName imageUrl price priceMin priceMax sales ratingStar
          commissionRate shopName productLink offerLink } } }"""

def chamar(palavra):
    payload = json.dumps({"query": QUERY % (json.dumps(palavra), SORT_VENDAS, POR_PALAVRA)})
    ts = str(int(time.time()))
    assinatura = hashlib.sha256((APP_ID + ts + payload + SECRET).encode()).hexdigest()
    cab = {"Content-Type": "application/json",
           "Authorization": "SHA256 Credential=%s, Timestamp=%s, Signature=%s" % (APP_ID, ts, assinatura)}
    r = requests.post(ENDPOINT, data=payload.encode(), headers=cab, timeout=30)
    j = r.json()
    if j.get("errors"):
        raise RuntimeError(json.dumps(j["errors"], ensure_ascii=False))
    return j["data"]["productOfferV2"]["nodes"] or []

def num(v, tipo=float):
    try:
        return tipo(v)
    except (TypeError, ValueError):
        return None

achados, falhas = {}, 0
for cat, lista in PALAVRAS.items():
    for palavra in lista:
        try:
            for n in chamar(palavra):
                achados[n["itemId"]] = (cat, n)
        except Exception as e:
            falhas += 1
            print("Falha em '%s': %s" % (palavra, e), file=sys.stderr)
        time.sleep(1.2)

if not achados:
    print("Nenhum produto coletado. Dados antigos mantidos.", file=sys.stderr)
    sys.exit(1)

fuso = datetime.timezone(datetime.timedelta(hours=-3))
hoje = datetime.datetime.now(fuso).date()
chave = lambda d: d.isoformat()

try:
    historico = json.load(open("data/historico.json"))
except Exception:
    historico = {}

vendas_hoje = {str(i): num(n.get("sales"), int) or 0 for i, (c, n) in achados.items()}
historico[chave(hoje)] = vendas_hoje
for d in sorted(historico)[:-40]:
    del historico[d]

def delta(item, dias):
    antes = historico.get(chave(hoje - datetime.timedelta(days=dias)))
    if antes is None or item not in antes:
        return None
    return max(0, vendas_hoje[item] - antes[item])

produtos = []
for i, (cat, n) in achados.items():
    item = str(i)
    produtos.append({
        "id": item, "nome": n.get("productName"), "cat": cat,
        "imagem": n.get("imageUrl"), "preco": num(n.get("price")),
        "precoMin": num(n.get("priceMin")), "precoMax": num(n.get("priceMax")),
        "comissao": num(n.get("commissionRate")), "vendas": vendas_hoje[item],
        "vendasDia": delta(item, 1), "vendasSemana": delta(item, 7), "vendasMes": delta(item, 30),
        "nota": num(n.get("ratingStar")), "loja": n.get("shopName"),
        "link": n.get("productLink"), "linkAfiliado": n.get("offerLink"),
    })
produtos.sort(key=lambda p: p["vendas"], reverse=True)
produtos = produtos[:TOTAL]

json.dump({"atualizado": datetime.datetime.now(fuso).isoformat(timespec="minutes"), "produtos": produtos},
          open("data/produtos.json", "w"), ensure_ascii=False)
json.dump(historico, open("data/historico.json", "w"))
print("OK: %d produtos, %d falhas" % (len(produtos), falhas))
