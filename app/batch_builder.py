from __future__ import annotations
import uuid
import json
import re
from typing import List, Dict, Any, Tuple, Optional

def build_batch_request(requests: list[dict]) -> tuple[str, dict]:
    """
    Construye un batch OData para SAP B1 Service Layer con un changeset.
    Cada 'request' debe tener: method, path, body, y opcionalmente content_id.
    """
    batch_boundary = f"batch_{uuid.uuid4().hex}"
    changeset_boundary = f"changeset_{uuid.uuid4().hex}"

    lines: list[str] = []
    ordered_cids: List[str] = []
    # Encabezado del batch (outer)
    lines.append(f"--{batch_boundary}")
    lines.append(f"Content-Type: multipart/mixed; boundary={changeset_boundary}")
    lines.append("")  # CRLF en blanco

    # Partes del changeset (inner)
    for i, req in enumerate(requests, start=1):
        method = req["method"].upper()
        path = req["path"]
        body = req.get("body", None)
        content_id = req.get("content_id", str(i))
        
        ordered_cids.append(content_id)
        
        lines.append(f"--{changeset_boundary}")
        lines.append("Content-Type: application/http")
        lines.append("Content-Transfer-Encoding: binary")
        lines.append(f"Content-ID: {content_id}")
        lines.append("")  # separa headers MIME de la petición HTTP interna

        # Línea de request interna y headers HTTP internos
        # Ojo: incluir HTTP/1.1; el path puede ser relativo (/b1s/v2/JournalEntries)
        lines.append(f"{method} {path} HTTP/1.1")
        lines.append("Accept: application/json")

        if method in ("POST", "PUT", "PATCH", "MERGE"):
            lines.append("Content-Type: application/json")
            lines.append("Prefer: return=representation")
            lines.append("")  # fin de headers HTTP internos
            # Cuerpo JSON
            lines.append(json.dumps(body, ensure_ascii=False))
        else:
            # GET/DELETE sin cuerpo
            lines.append("")  # fin de headers HTTP internos

    # Cierre del changeset y del batch
    lines.append(f"--{changeset_boundary}--")
    lines.append(f"--{batch_boundary}--")

    body = "\r\n".join(lines) + "\r\n"
    headers = {
        "Content-Type": f"multipart/mixed; boundary={batch_boundary}"
    }
    return body, headers,ordered_cids

def build_batch_request_older(requests: list[dict]) -> tuple[str, dict]:
    """
    Builds a multipart/mixed batch request body and headers.
    Each request in the list should be a dict with 'method', 'path', and 'body'.
    """
    batch_id = f"batch_{uuid.uuid4()}"
    boundary = f"batch_{uuid.uuid4()}"
    # print(f"body: {batch_id}")
    
    parts = []
    for req in requests:
        part = "--" + boundary + "\r\n"
        part += "Content-Type: application/http\r\n"
        part += "Content-Transfer-Encoding: binary\r\n\r\n"
        part += f"{req['method']} {req['path']}\r\n"
        part += "Content-Type: application/json\r\n\r\n"
        part += "Prefer: return=representation\r\n\r\n"
        part += json.dumps(req['body'])
        parts.append(part)

    body = "\r\n".join(parts)
    body += "\r\n--" + boundary + "--\r\n"

    headers = {
        "Content-Type": f"multipart/mixed; boundary={boundary}"
    }
    return body, headers

def parse_batch_response(response_text: str, boundary: str) -> List[Dict[str, Any]]:
    """
    Parse a multipart/mixed $batch response (SAP B1 Service Layer).
    - Maneja multipart anidado (changesetresponse).
    - Extrae status, headers, Content-ID y body (JSON si es posible).
    Devuelve una lista aplanada de sub-respuestas.
    """
    if not boundary:
        raise ValueError("Boundary not found in Content-Type header")

    def _norm(s: str) -> str:
        # normaliza saltos de línea: conserva CRLF si existe, pero asegura al menos '\n'
        return s.replace('\r\n', '\n')

    def _parse_headers(hs: str) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        for line in hs.split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue
            k, v = line.split(':', 1)
            headers[k.strip().lower()] = v.strip()
        return headers

    def _find_boundary_in_ct(ct: str) -> Optional[str]:
        # Content-Type: multipart/mixed; boundary=changesetresponse_abc123
        m = re.search(r'boundary="?([^";]+)"?', ct, flags=re.I)
        return m.group(1) if m else None

    def _split_headers_body(part_text: str) -> Tuple[str, str]:
        # Busca doble salto de línea (CRLF o LF)
        idx = part_text.find('\r\n\r\n')
        if idx >= 0:
            return part_text[:idx], part_text[idx+4:]
        idx = part_text.find('\n\n')
        if idx >= 0:
            return part_text[:idx], part_text[idx+2:]
        # Sin separación clara: todo como body
        return "", part_text

    def _parse_application_http(body_text: str, outer_headers: Dict[str, str]) -> Dict[str, Any]:
        """
        Estructura típica:
            HTTP/1.1 201 Created\r\n
            Header: ...\r\n
            ...\r\n
            \r\n
            {json...}
        """
        bt = _norm(body_text)
        # status line
        first_newline = bt.find('\n')
        if first_newline == -1:
            status_line = bt.strip()
            rest = ""
        else:
            status_line = bt[:first_newline].strip()
            rest = bt[first_newline+1:]

        # headers internos + body
        in_hdrs_str, in_body = _split_headers_body(rest)
        in_headers = _parse_headers(in_hdrs_str)

        # status code y texto
        status_code = 0
        status_text = ""
        try:
            # Ej: "HTTP/1.1 201 Created"
            parts = status_line.split(' ', 2)
            status_code = int(parts[1]) if len(parts) > 1 else 0
            status_text = parts[2] if len(parts) > 2 else ""
        except Exception:
            status_text = status_line or ""

        # Content-ID puede venir en headers externos o internos
        content_id = outer_headers.get('content-id') or in_headers.get('content-id')

        # Body → intenta JSON
        raw_body = in_body.strip()
        body_obj = None
        if raw_body:
            try:
                body_obj = json.loads(raw_body)
            except Exception:
                body_obj = None

        return {
            "status_code": status_code,
            "status_text": status_text,
            "content_id": content_id,
            "headers": outer_headers,
            "http_headers": in_headers,
            "body": body_obj,
            "raw_body": raw_body
        }

    def _iter_parts(mixed_text: str, b: str) -> List[str]:
        # Divide por el boundary superior. No elimina sub-boundaries anidados.
        # El preámbulo puede aparecer antes del primer boundary.
        parts = mixed_text.split(f"--{b}")
        out = []
        for p in parts:
            p = p.strip()
            if not p or p == "--":
                continue
            out.append(p)
        return out

    def _parse_multipart(mixed_text: str, b: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for raw_part in _iter_parts(mixed_text, b):
            # Cada part: headers + body (que puede ser multipart o application/http)
            headers_str, body_str = _split_headers_body(raw_part)
            headers = _parse_headers(_norm(headers_str))
            ct = headers.get('content-type', '').lower()

            if ct.startswith('multipart/mixed'):
                inner_b = _find_boundary_in_ct(ct)
                if not inner_b:
                    # Si no podemos detectar el inner boundary, devolvemos parte cruda
                    results.append({
                        "status_code": 0,
                        "status_text": "",
                        "content_id": headers.get('content-id'),
                        "headers": headers,
                        "http_headers": {},
                        "body": None,
                        "raw_body": body_str.strip()
                    })
                else:
                    # recursion: parsea subpartes (cambios del changeset)
                    inner_results = _parse_multipart(body_str, inner_b)
                    results.extend(inner_results)
            elif 'application/http' in ct:
                results.append(_parse_application_http(body_str, headers))
            else:
                # Parte “simple”: intenta interpretar como JSON; si no, deja raw.
                rb = body_str.strip()
                obj = None
                if rb:
                    try:
                        obj = json.loads(rb)
                    except Exception:
                        obj = None
                results.append({
                    "status_code": 0,
                    "status_text": "",
                    "content_id": headers.get('content-id'),
                    "headers": headers,
                    "http_headers": {},
                    "body": obj,
                    "raw_body": rb
                })
        return results

    return _parse_multipart(response_text, boundary)