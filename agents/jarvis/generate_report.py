import json
import urllib.request
import subprocess
import os
from collections import defaultdict
from datetime import datetime

# 1. Fetch data from Pluggy
cred_file = "/home/node/.openclaw/workspace-lucia/.pluggy_credentials"
with open(cred_file) as f:
    creds = json.load(f)

url = creds["apiUrl"] + "/auth"
payload = json.dumps({"clientId": creds["clientId"], "clientSecret": creds["clientSecret"]}).encode("utf-8")
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req) as resp:
    api_key = json.loads(resp.read().decode())["apiKey"]

# Fetch accounts balance summary
accounts_info = []
for item_id in creds["itemIds"]:
    acc_url = creds["apiUrl"] + "/accounts?itemId=" + item_id
    req = urllib.request.Request(acc_url, headers={"X-API-KEY": api_key})
    with urllib.request.urlopen(req) as resp:
        accounts = json.loads(resp.read().decode())["results"]
        for a in accounts:
            accounts_info.append({
                "name": a.get("name"),
                "number": a.get("number"),
                "type": a.get("type"),
                "subtype": a.get("subtype"),
                "balance": a.get("balance", 0.0)
            })

all_txs = []
for item_id in creds["itemIds"]:
    acc_url = creds["apiUrl"] + "/accounts?itemId=" + item_id
    req = urllib.request.Request(acc_url, headers={"X-API-KEY": api_key})
    with urllib.request.urlopen(req) as resp:
        accounts = json.loads(resp.read().decode())["results"]
    for acc in accounts:
        acc_id = acc["id"]
        acc_name = acc["name"]
        tx_url = creds["apiUrl"] + "/transactions?accountId=" + acc_id + "&from=2026-09-21T00:00:00Z&to=2026-09-27T23:59:59Z&pageSize=500"
        req = urllib.request.Request(tx_url, headers={"X-API-KEY": api_key})
        with urllib.request.urlopen(req) as resp:
            txs = json.loads(resp.read().decode())["results"]
            for t in txs:
                t["account_name"] = acc_name
                all_txs.append(t)

# Sort transactions chronologically reverse for table display (newest first)
all_txs.sort(key=lambda x: x["date"], reverse=True)

# Category mapping to Portuguese
CATEGORY_MAP = {
    "Groceries": "Supermercado & Alimentação",
    "Transfer - PIX": "Transferências PIX",
    "Transfers": "Pagamentos & Faturas",
    "Taxi and ride-hailing": "Transporte (Uber/99)",
    "Investments": "Investimentos & Aplicações",
    "Pharmacy": "Farmácia & Saúde",
    "Pet supplies and vet": "Pet Shop & Veterinário",
    "Services": "Serviços & Assinaturas",
    "Telecommunications": "Telefonia & Recarga",
    "Education": "Educação & Cursos",
    "Same person transfer": "Transferência Entre Contas",
    "None": "Outros"
}

total_debit = 0.0
total_credit = 0.0
cat_debits = defaultdict(float)
cat_credits = defaultdict(float)

processed_txs = []

for t in all_txs:
    amt = t["amount"]
    raw_cat = t.get("category") or "None"
    pt_cat = CATEGORY_MAP.get(raw_cat, raw_cat)
    
    # Parse date
    dt = datetime.fromisoformat(t["date"].replace("Z", "+00:00"))
    date_str = dt.strftime("%d/%m/%Y %H:%M")
    
    is_debit = (t["type"] == "DEBIT" or amt < 0)
    abs_amt = abs(amt)
    
    if is_debit:
        total_debit += abs_amt
        cat_debits[pt_cat] += abs_amt
    else:
        total_credit += abs_amt
        cat_credits[pt_cat] += abs_amt
        
    processed_txs.append({
        "date": date_str,
        "description": t.get("description", "Sem descrição"),
        "category": pt_cat,
        "amount": abs_amt,
        "is_debit": is_debit,
        "account": t.get("account_name", "")
    })

saldo_semana = total_credit - total_debit

# Sort category debits for chart / list
sorted_debits = sorted(cat_debits.items(), key=lambda x: x[1], reverse=True)

# 2. Build HTML
html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Relatório Financeiro Semanal — J.A.R.V.I.S.</title>
    <style>
        @page {{
            size: A4;
            margin: 15mm;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 0;
            font-size: 13px;
            line-height: 1.4;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #334155;
            padding-bottom: 16px;
            margin-bottom: 20px;
        }}
        .brand {{
            font-size: 22px;
            font-weight: 800;
            color: #38bdf8;
            letter-spacing: 1px;
        }}
        .brand span {{
            color: #94a3b8;
            font-size: 14px;
            font-weight: 400;
        }}
        .period {{
            text-align: right;
            color: #94a3b8;
            font-size: 12px;
        }}
        .period-title {{
            font-size: 14px;
            font-weight: 600;
            color: #f1f5f9;
        }}
        
        .kpi-container {{
            display: flex;
            gap: 12px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            flex: 1;
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 14px;
        }}
        .kpi-title {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #94a3b8;
            margin-bottom: 6px;
        }}
        .kpi-value {{
            font-size: 20px;
            font-weight: 700;
        }}
        .val-red {{ color: #f87171; }}
        .val-green {{ color: #4ade80; }}
        .val-blue {{ color: #38bdf8; }}
        
        .section-title {{
            font-size: 16px;
            font-weight: 700;
            color: #f1f5f9;
            margin-top: 24px;
            margin-bottom: 12px;
            border-left: 4px solid #38bdf8;
            padding-left: 8px;
        }}
        
        .categories-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 24px;
        }}
        .cat-card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 10px 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .cat-name {{
            font-weight: 600;
            color: #e2e8f0;
        }}
        .cat-bar-bg {{
            height: 6px;
            background: #334155;
            border-radius: 3px;
            margin-top: 4px;
            overflow: hidden;
        }}
        .cat-bar-fill {{
            height: 100%;
            background: #f87171;
            border-radius: 3px;
        }}
        .cat-amount {{
            text-align: right;
            font-weight: 700;
            color: #f87171;
        }}
        .cat-pct {{
            font-size: 11px;
            color: #94a3b8;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            background: #1e293b;
            border-radius: 8px;
            overflow: hidden;
        }}
        th {{
            background: #0f172a;
            color: #94a3b8;
            text-align: left;
            padding: 8px 12px;
            font-size: 11px;
            text-transform: uppercase;
            border-bottom: 1px solid #334155;
        }}
        td {{
            padding: 8px 12px;
            border-bottom: 1px solid #334155;
            color: #cbd5e1;
            font-size: 12px;
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        .tx-debit {{
            color: #f87171;
            font-weight: 600;
        }}
        .tx-credit {{
            color: #4ade80;
            font-weight: 600;
        }}
        .footer {{
            margin-top: 30px;
            text-align: center;
            font-size: 11px;
            color: #64748b;
            border-top: 1px solid #334155;
            padding-top: 12px;
        }}
    </style>
</head>
<body>

    <div class="header">
        <div class="brand">
            J.A.R.V.I.S. <span>| Relatório Financeiro Executivo</span>
        </div>
        <div class="period">
            <div class="period-title">Semana Conciliada</div>
            21/09/2026 a 27/09/2026 (Open Finance - Pluggy)
        </div>
    </div>

    <div class="kpi-container">
        <div class="kpi-card">
            <div class="kpi-title">Total de Saídas (Débitos)</div>
            <div class="kpi-value val-red">R$ {total_debit:,.2f}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Total de Entradas (Créditos)</div>
            <div class="kpi-value val-green">R$ {total_credit:,.2f}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Resultado da Semana</div>
            <div class="kpi-value {'val-green' if saldo_semana >= 0 else 'val-red'}">
                R$ {saldo_semana:,.2f}
            </div>
        </div>
    </div>

    <div class="section-title">Detalhamento dos Gastos por Categoria</div>
    <div class="categories-grid">
"""

for cat, val in sorted_debits:
    pct = (val / total_debit * 100) if total_debit > 0 else 0
    html_content += f"""
        <div class="cat-card">
            <div style="flex: 1; padding-right: 12px;">
                <div class="cat-name">{cat}</div>
                <div class="cat-bar-bg">
                    <div class="cat-bar-fill" style="width: {pct:.1f}%;"></div>
                </div>
            </div>
            <div>
                <div class="cat-amount">R$ {val:,.2f}</div>
                <div class="cat-pct">{pct:.1f}% do total</div>
            </div>
        </div>
    """

html_content += """
    </div>

    <div class="section-title">Extrato Consolidado da Semana (48 Transações)</div>
    <table>
        <thead>
            <tr>
                <th>Data / Hora</th>
                <th>Descrição / Favorecido</th>
                <th>Categoria</th>
                <th>Conta</th>
                <th style="text-align: right;">Valor</th>
            </tr>
        </thead>
        <tbody>
"""

for tx in processed_txs:
    cls = "tx-debit" if tx["is_debit"] else "tx-credit"
    sign = "-" if tx["is_debit"] else "+"
    html_content += f"""
            <tr>
                <td style="white-space: nowrap;">{tx["date"]}</td>
                <td>{tx["description"]}</td>
                <td>{tx["category"]}</td>
                <td>{tx["account"]}</td>
                <td style="text-align: right;" class="{cls}">{sign} R$ {tx["amount"]:,.2f}</td>
            </tr>
    """

html_content += """
        </tbody>
    </table>

    <div class="footer">
        Relatório financeiro gerado automaticamente pelo J.A.R.V.I.S. via Open Finance Brasil (Pluggy API) • 28/09/2026
    </div>

</body>
</html>
"""

html_file = "/home/node/.openclaw/workspace-jarvis/media/relatorio_semanal.html"
pdf_file = "/home/node/.openclaw/workspace-jarvis/media/relatorio_semanal.pdf"

with open(html_file, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"HTML saved to {html_file}")

# Convert HTML to PDF via headless Chromium
cmd = ["chromium", "--headless", "--no-sandbox", "--disable-gpu", f"--print-to-pdf={pdf_file}", html_file]
res = subprocess.run(cmd, capture_output=True, text=True)
print("Chromium exit code:", res.returncode)
print(f"PDF generated: {os.path.exists(pdf_file)} ({os.path.getsize(pdf_file) if os.path.exists(pdf_file) else 0} bytes)")
