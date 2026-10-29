from services import sftp_storage 
from openpyxl import load_workbook

def get_proposal_file(company):
    try:
        file_names = sftp_storage.list_dir(company)
    except FileNotFoundError:
        return None
    for file_name in file_names:
        if (file_name.endswith(".xlsx")):
            return sftp_storage.load(f"{company}/{file_name}")
    return None

def get_list_from_excel(company):
    excel = get_proposal_file(company)
    if excel is None:
        return None
    wb = load_workbook(excel, read_only=True)
    ws = wb["Mapping Proposal"]
    titles = []
    for cell in ws[2]:
        titles.append(cell.value)
    mappings = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        record = dict(zip(titles, row))
        if record.get("Mapping ID") is None:
            continue
        mapping = {                   
        "id": record.get("Mapping ID"),
        "bronveld": record.get("Source full path"),
        "doelveld": record.get("Target field name"),
        "zekerheid": record.get("Confidence %"),
        "opmerking": record.get("Confidence reason")
    }
        mappings.append(mapping) 
    wb.close()
    return mappings