import requests
from config import helius_token

url = f"https://mainnet.helius-rpc.com/?api-key={helius_token}"

payload = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "getTransactionsForAddress",
    "params": [
        "Vote111111111111111111111111111111111111111",
        {
            "transactionDetails": "signatures",
            "limit": 50,
            "sortOrder": "desc",
            "filters": {
                "status": "succeeded",
                "slot": {
                    "gte": 1000,
                    "lt": 2000
                },
                "tokenTransfer": {
                    "direction": "in",
                    "mint": "CPUnMyvhSAoEfEqyZ67bj6iDkCLkHmJvnTafJ6NJpump"
                }
            }
        }
    ]
}
headers = {"Content-Type": "application/json"}

response = requests.post(url, json=payload, headers=headers)

print(response.text)