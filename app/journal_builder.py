def build_journal_entry(cab: dict, lines: list[dict], *, local_currency: str = "PEN") -> dict:
    je = {
        "ReferenceDate": '', #cab.get("ReferenceDate") or cab.get("TaxDate"),
        "TaxDate":       '', # cab.get("TaxDate") or cab.get("ReferenceDate"),
        "DueDate":       '', #cab.get("DueDate") or cab.get("ReferenceDate"),
        "Memo":          '', #cab.get("Memo") or f"Asiento {cab.get('JdtNum') or ''}",
        "Reference2":    '', #cab.get("Reference2") or str(cab.get("JdtNum")) or '',
        "ProjectCode": '',
        "TransactionCode":''
    }
    if cab.get("ProjectCode"):     je["ProjectCode"] = cab["ProjectCode"] or ''
    if cab.get("TransactionCode"): je["TransactionCode"] = cab["TransactionCode"] or ""
    
    sap_lines = []
    for l in lines:
        # print(l["ShortName"] or l["shortname"])
        out = {
            "Debit":  float(l.get("Debit")  or 0),
            "Credit": float(l.get("Credit") or 0),
            "LineMemo": l.get("LineMemo") or je["Memo"],
            'FCCurrency':'',
        }
        
        # para las cabeceras
        je["Memo"]=l.get("Memo")
        je["TaxDate"]=l.get("DueDate")
        je["ReferenceDate"]=l.get("DueDate")
        je["DueDate"]=l.get("DueDate")
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
        
        # Mapeo de Centros de Costo (OcrCode1-5 internos -> U_RS_D1-5 de SAP como UDFs)
        for i in range(1, 6):
            internal_key = f"OcrCode{i}"
            sap_key = f"U_RS_D{i}"
            val = l.get(internal_key)
            # Evitar enviar el nombre de la columna como valor (ej: "OcrCode1")
            if val and str(val).strip() not in (internal_key, ""):
                out[sap_key] = val

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
    return je
