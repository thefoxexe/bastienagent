import aiohttp

_CURRENCY_NAMES = {
    "CHF": "Franc suisse", "EUR": "Euro", "USD": "Dollar américain",
    "GBP": "Livre sterling", "JPY": "Yen japonais", "CAD": "Dollar canadien",
    "AUD": "Dollar australien", "SEK": "Couronne suédoise", "NOK": "Couronne norvégienne",
    "DKK": "Couronne danoise", "CNY": "Yuan chinois", "HKD": "Dollar de Hong Kong",
    "SGD": "Dollar de Singapour", "NZD": "Dollar néo-zélandais", "MXN": "Peso mexicain",
}


async def convert(amount: float, from_curr: str, to_curr: str) -> dict:
    from_curr = from_curr.upper().strip()
    to_curr = to_curr.upper().strip()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.frankfurter.app/latest",
            params={"from": from_curr, "to": to_curr, "amount": amount},
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Erreur API devises ({resp.status})")
            data = await resp.json()
    result = data["rates"].get(to_curr)
    if result is None:
        raise RuntimeError(f"Devise '{to_curr}' non supportée")
    return {
        "amount": amount,
        "from_currency": from_curr,
        "to_currency": to_curr,
        "result": result,
        "rate": result / amount,
        "from_name": _CURRENCY_NAMES.get(from_curr, from_curr),
        "to_name": _CURRENCY_NAMES.get(to_curr, to_curr),
    }
