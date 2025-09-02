def build_journal_entry(cab: dict, lines: list[dict], *, local_currency: str = "PEN") -> dict:
    je = {
        "ReferenceDate": cab.get("ReferenceDate") or cab.get("TaxDate"),
        "TaxDate":       cab.get("TaxDate") or cab.get("ReferenceDate"),
        "DueDate":       cab.get("DueDate") or cab.get("ReferenceDate"),
        "Memo":          cab.get("Memo") or f"Asiento {cab.get('JdtNum') or ''}",
        "Reference2":    cab.get("Reference2") or str(cab.get("JdtNum")) or '',
        "ProjectCode": '',
        "TransactionCode":''
    }
    if cab.get("ProjectCode"):     je["ProjectCode"] = cab["ProjectCode"] or ''
    if cab.get("TransactionCode"): je["TransactionCode"] = cab["TransactionCode"] or ""
    
    sap_lines = []
    for l in lines:
        # print(l["ShortName"] or l["shortname"])
        out = {
            "AccountCode": l["AccountCode"],
            "Debit":  float(l.get("Debit")  or 0),
            "Credit": float(l.get("Credit") or 0),
            "LineMemo": l.get("LineMemo") or je["Memo"],
            "Reference2":'',
            "ReferenceDate2":'',
            'ProjectCode':'',
            'CostingCode':'',
            'FCCurrency':'',
            "ShortName": l.get("ShortName",None) or l.get("shortname",None)
        }
        
        for k in ["CostingCode","ProjectCode","Reference2","Reference1","U_INFOPE01","U_INFOPE02","LineNum"]:
            if l.get(k): out[k] = l[k] or ''
        if l.get("FCCurrency") and l["FCCurrency"].upper() != local_currency:
            out["FCCurrency"] = l["FCCurrency"].upper()
            if out["Debit"]  > 0 and l.get("FCDebit")  is not None: out["FCDebit"]  = float(l["FCDebit"])
            if out["Credit"] > 0 and l.get("FCCredit") is not None: out["FCCredit"] = float(l["FCCredit"])
        sap_lines.append(out)
    

    je["JournalEntryLines"] = sap_lines
    return je
