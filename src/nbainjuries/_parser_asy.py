from os import PathLike
import pandas as pd
import PyPDF2
from io import BytesIO
from ._exceptions import URLRetrievalError, LocalRetrievalError
from ._util import _build_injrep, _validate_headers, _pagect_localpdf
from ._constants import requestheaders, rowgap_params2526
import asyncio
import aiohttp
from aiohttp import ClientSession
import threading
import jpype
# import jpype.imports
# from tabula.backend import jar_path
# jpype.addClassPath(jar_path())
# jvmpath = jpype.getDefaultJVMPath()
# java_opts = ["-Dfile.encoding=UTF-8", "-Xrs"]
# jpype.startJVM(jvmpath, *java_opts, convertStrings=False)
import tabula

_jvm_lock = threading.Lock()


async def validate_irurl_async(filepath: str | PathLike, session: ClientSession, **kwargs):
    """
    :param filepath: url of report
    :param session:
    :param kwargs: custom headers
    :return: response object (if validation succeeds)
    """
    try:
        async with session.get(filepath, **kwargs) as resp:
            resp.raise_for_status()
            print(f"Validated {filepath.split('/')[-1].rsplit('.', 1)[0]}.")
            return await resp.read()
    except aiohttp.ClientError as e_gen:
        print(f"Failed validation - {filepath.split('/')[-1].rsplit('.', 1)[0]}.")
        raise URLRetrievalError(filepath, e_gen)
        ## TODO logging?


def _read_pdfjvmwrap(*args, **kwargs):
    """
    Wrapper to coordinate jpype/JVM
    """
    with _jvm_lock:
        if not jpype.isJVMStarted():
            jvmpath = jpype.getDefaultJVMPath()
            java_opts = ["-Dfile.encoding=UTF-8", "-Xrs"]
            jpype.startJVM(jvmpath, *java_opts, convertStrings=False)
        result = tabula.read_pdf(*args, **kwargs)
    return result


async def extract_irurl_async(filepath: str | PathLike, session: ClientSession, area_headpg: list, cols_headpg: list,
                      area_otherpgs: list | None = None, cols_otherpgs: list | None = None,
                      rowgap: float = rowgap_params2526, **kwargs) -> pd.DataFrame:
    """
    :param filepath: url of report
    :param session:
    :param area_headpg: area boundaries of first pg of pdf
    :param cols_headpg: column boundaries of first pg of pdf
    :param area_otherpgs: area boundaries of other pgs of pdf if needed
    :param cols_otherpgs: column boundaries of other pgs of pdf if needed
    :param rowgap: largest gap between the tops of consecutive lines of one row
    :param kwargs: custom headers
    :return:
    """
    pdf_content = await validate_irurl_async(filepath, session, **kwargs)
    pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_content))
    pdf_numpgs = len(pdf_reader.pages)

    if area_otherpgs is None:
        area_otherpgs = area_headpg
    if cols_otherpgs is None:
        cols_otherpgs = cols_headpg

    # First pg - json output keeps where each line sits on the page
    tables_headpg = await asyncio.to_thread(_read_pdfjvmwrap, filepath, stream=True,
                                            user_agent=requestheaders['User-Agent'], area=area_headpg,
                                            columns=cols_headpg, pages=1, output_format='json')
    # Following pgs
    tables_otherpgs = []  # default to empty if single pg
    if pdf_numpgs >= 2:
        tables_otherpgs = await asyncio.to_thread(_read_pdfjvmwrap, filepath, stream=True,
                                                  user_agent=requestheaders['User-Agent'], area=area_otherpgs,
                                                  columns=cols_otherpgs, pages='2-' + str(pdf_numpgs),
                                                  output_format='json')
    # Processing
    return _build_injrep(tables_headpg + tables_otherpgs, pdf_numpgs, rowgap)


async def extract_irlocal_async(filepath: str | PathLike, area_headpg: list, cols_headpg: list,
                        area_otherpgs: list | None = None, cols_otherpgs: list | None = None,
                        rowgap: float = rowgap_params2526) -> pd.DataFrame:
    try:
        pdf_numpgs = await asyncio.to_thread(_pagect_localpdf, filepath)
    except (FileNotFoundError, PermissionError) as e_gen:
        raise LocalRetrievalError(filepath, e_gen)
        ## potential logging
        # archive FileNotFoundError(f'Could not open {str(filepath)} due to {e_gen}.')

    if area_otherpgs is None:
        area_otherpgs = area_headpg
    if cols_otherpgs is None:
        cols_otherpgs = cols_headpg

    # First page - json output keeps where each line sits on the page
    tables_headpg = await asyncio.to_thread(_read_pdfjvmwrap, filepath, stream=True, area=area_headpg,
                                            columns=cols_headpg, pages=1, output_format='json')
    # Following pgs
    tables_otherpgs = []  # default to empty if single pg
    if pdf_numpgs >= 2:
        tables_otherpgs = await asyncio.to_thread(_read_pdfjvmwrap, filepath, stream=True, area=area_otherpgs,
                                                  columns=cols_otherpgs, pages='2-' + str(pdf_numpgs),
                                                  output_format='json')
    # Processing
    return _build_injrep(tables_headpg + tables_otherpgs, pdf_numpgs, rowgap)

