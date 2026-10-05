from os import PathLike
import pandas as pd
import tabula
import PyPDF2
from io import BytesIO
import requests
from ._exceptions import URLRetrievalError, LocalRetrievalError
from ._util import _build_injrep, _validate_headers, _pagect_localpdf
from ._constants import requestheaders, rowgap_params2526


def validate_injrepurl(filepath: str | PathLike, **kwargs) -> requests.Response:
    """
    :param filepath: url of report
    :param kwargs: custom headers
    :return: response object (if validation succeeds)
    """
    try:
        resp = requests.get(filepath, **kwargs)
        resp.raise_for_status()
        print(f"Validated {filepath.split('/')[-1].rsplit('.', 1)[0]}.")
        return resp
    except requests.exceptions.RequestException as e_gen:
        print(f"Failed validation - {filepath.split('/')[-1].rsplit('.', 1)[0]}.")
        raise URLRetrievalError(filepath, e_gen)


def extract_injrepurl(filepath: str | PathLike, area_headpg: list, cols_headpg: list,
                      area_otherpgs: list | None = None, cols_otherpgs: list | None = None,
                      rowgap: float = rowgap_params2526, **kwargs) -> pd.DataFrame:
    """
    :param filepath: url of report
    :param area_headpg: area boundaries of first pg of pdf
    :param cols_headpg: column boundaries of first pg of pdf
    :param area_otherpgs: area boundaries of other pgs of pdf if needed
    :param cols_otherpgs: column boundaries of other pgs of pdf if needed
    :param rowgap: largest gap between the tops of consecutive lines of one row
    :param kwargs: custom headers
    """
    resp = validate_injrepurl(filepath, **kwargs)
    pdf_content = resp.content
    pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_content))
    pdf_numpgs = len(pdf_reader.pages)

    if area_otherpgs is None:
        area_otherpgs = area_headpg
    if cols_otherpgs is None:
        cols_otherpgs = cols_headpg

    # First pg - json output keeps where each line sits on the page
    tables_headpg = tabula.read_pdf(filepath, stream=True, user_agent=requestheaders['User-Agent'], area=area_headpg,
                                    columns=cols_headpg, pages=1, output_format='json')
    # Following pgs
    tables_otherpgs = []  # default to empty if single pg
    if pdf_numpgs >= 2:
        tables_otherpgs = tabula.read_pdf(filepath, stream=True, user_agent=requestheaders['User-Agent'],
                                          area=area_otherpgs, columns=cols_otherpgs, pages='2-' + str(pdf_numpgs),
                                          output_format='json')
    # Processing
    return _build_injrep(tables_headpg + tables_otherpgs, pdf_numpgs, rowgap)


def extract_injreplocal(filepath: str | PathLike, area_headpg: list, cols_headpg: list,
                        area_otherpgs: list | None = None, cols_otherpgs: list | None = None,
                        rowgap: float = rowgap_params2526) -> pd.DataFrame:
    try:
        pdf_numpgs = _pagect_localpdf(filepath)
    except (FileNotFoundError, PermissionError) as e_gen:
        raise LocalRetrievalError(filepath, e_gen)
        # archive FileNotFoundError(f'Could not open {str(filepath)} due to {e_gen}.')

    if area_otherpgs is None:
        area_otherpgs = area_headpg
    if cols_otherpgs is None:
        cols_otherpgs = cols_headpg

    # First page - json output keeps where each line sits on the page
    tables_headpg = tabula.read_pdf(filepath, stream=True, area=area_headpg,
                                    columns=cols_headpg, pages=1, output_format='json')
    # Following pgs
    tables_otherpgs = []  # default to empty if single pg
    if pdf_numpgs >= 2:
        tables_otherpgs = tabula.read_pdf(filepath, stream=True, area=area_otherpgs,
                                          columns=cols_otherpgs, pages='2-' + str(pdf_numpgs), output_format='json')
    # Processing
    return _build_injrep(tables_headpg + tables_otherpgs, pdf_numpgs, rowgap)

