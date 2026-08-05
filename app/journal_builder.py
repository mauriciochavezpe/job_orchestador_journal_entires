def build_journal_entry(cab: dict, lines: list[dict], *, local_currency: str = "PEN") -> dict:
    je = {
        "ReferenceDate": cab.get("ReferenceDate") or cab.get("ReferenceDate") or '',
        "TaxDate":       cab.get("TaxDate") or cab.get("TaxDate") or '',
        "DueDate":       cab.get("DueDate") or cab.get("ReferenceDate") or '',
        "Memo":          cab.get("Memo") or f"Asiento {cab.get('JdtNum') or ''}",
        "Reference2":    cab.get("Reference2") or str(cab.get("JdtNum")) or '',
        "ProjectCode":   cab.get("ProjectCode") or '',
        "TransactionCode": cab.get("TransactionCode") or ""
    }
    
    # DEBUG: mostrar cabecera
    # print(f"[DEBUG JOURNAL] Cabecera del asiento:\n{je}\n")
    
    sap_lines = []
    for l in lines:
        # print(l["ShortName"] or l["shortname"])
        out = {
            "Debit":  float(l.get("Debit")  or 0),
            "Credit": float(l.get("Credit") or 0),
            "LineMemo": l.get("LineMemo") or je["Memo"],
            'FCCurrency':'',
            #'FCCurrency':l.get('FCCurrency') or "PEN",
        }
        # Lógica para Cuentas Asociadas vs Cuentas Normales
        # Siempre enviamos AccountCode para que SAP use la cuenta explícita del asiento.
        # Si además hay un ShortName (Socio de Negocio / CardCode) distinto al AccountCode,
        # lo enviamos también — SAP acepta ambos campos en la misma línea.
        # NOTA: omitir AccountCode causaba que SAP usara la cuenta de control del BP por defecto.
        acc_code = l.get("AccountCode") or l.get("accountcode")
        sn = l.get("ShortName") or l.get("shortname")
        if acc_code:
            out["AccountCode"] = acc_code
        if sn and sn != acc_code:
            out["ShortName"] = sn
        

        # Mapeo de Centros de Costo:
        # - Campos nativos SAP: CostingCode (dim1), CostingCode2-5
        # - UDFs del asiento: U_RS_D1-5
        # El campo "CostingCode" (sin número) equivale a la dimensión 1.
        costing_fields = {
            "CostingCode":  ("CostingCode",  "U_RS_D1"),
            "CostingCode2": ("CostingCode2", "U_RS_D2"),
            "CostingCode3": ("CostingCode3", "U_RS_D3"),
            "CostingCode4": ("CostingCode4", "U_RS_D4"),
            "CostingCode5": ("CostingCode5", "U_RS_D5"),
        }
        for src_key, (sap_native, sap_udf) in costing_fields.items():
            val = l.get(src_key)
            if val and str(val).strip() not in (src_key, ""):
                out[sap_native] = val  # campo nativo SAP
                out[sap_udf]    = val  # UDF del asiento

        # Empleado (OHEM.Code) resuelto desde U_CE_PVAS / LicTradNum del payload
        if l.get("EmployeeID") is not None and str(l["EmployeeID"]).strip() not in ("", "None", "0"):
            out["EmployeeID"] = int(l["EmployeeID"])

        # Otros campos
        for k in ["ProjectCode","Reference2","Reference1","U_INFOPE01","U_INFOPE02","LineNum"]:
            if l.get(k): out[k] = l[k] or ''
        if l.get("FCCurrency") and l["FCCurrency"].upper() != local_currency:
            out["FCCurrency"] = l["FCCurrency"].upper()
            if out["Debit"]  > 0 and l.get("FCDebit")  is not None: out["FCDebit"]  = float(l["FCDebit"])
            if out["Credit"] > 0 and l.get("FCCredit") is not None: out["FCCredit"] = float(l["FCCredit"])
        sap_lines.append(out)
    

    je["JournalEntryLines"] = sap_lines
    
    # DEBUG: mostrar JSON final
    import json
    # print(f"[DEBUG JOURNAL] JSON completo del asiento:\n{json.dumps(je, indent=2, default=str)}\n")
    
    return je
