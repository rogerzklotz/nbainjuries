from os import path, PathLike
from datetime import datetime
import re
import pandas as pd
import PyPDF2
from . import _constants
from ._exceptions import DataValidationError


# URL format boundaries due to policy change in reporting
_DT_LEGACYFMT1 = datetime(2025, 12, 19, 15, 30)  # legacy 1 inclusive
_DT_LEGACYFMT2 = datetime(2025, 12, 19, 16, 45)  # legacy 2 inclusive
_DT_NEWFMT15M = datetime(2025, 12, 22, 9, 0)  # new inclusive
_STRF_LEGACY = '%I%p'
_STRF_NEW = '%I_%M%p'


def _gen_url(timestamp: datetime) -> str:
    URLstem_date = timestamp.date().strftime('%Y-%m-%d')
    if timestamp <= _DT_LEGACYFMT1:
        URLstem_time = (timestamp.replace(minute=0)).time().strftime(_STRF_LEGACY)
    elif _DT_LEGACYFMT2 <= timestamp < _DT_NEWFMT15M:
        URLstem_time = (timestamp.replace(minute=0)).time().strftime(_STRF_LEGACY)
    elif timestamp >= _DT_NEWFMT15M:
        URLstem_time = timestamp.time().strftime(_STRF_NEW)
    else:  # gap btn the _DT_LEGACYFMT1/_DT_LEGACYFMT2
        raise ValueError(f"Invalid Report Time {timestamp} entered.")
    return _constants.urlstem_injreppdf.replace('*', URLstem_date + '_' + URLstem_time)


def _gen_filepath(timestamp: datetime, directorypath: str | PathLike) -> str:
    URLstem_date = timestamp.date().strftime('%Y-%m-%d')
    if timestamp <= _DT_LEGACYFMT1:
        URLstem_time = (timestamp.replace(minute=0)).time().strftime(_STRF_LEGACY)
    elif _DT_LEGACYFMT2 <= timestamp < _DT_NEWFMT15M:
        URLstem_time = (timestamp.replace(minute=0)).time().strftime(_STRF_LEGACY)
    elif timestamp >= _DT_NEWFMT15M:
        URLstem_time = timestamp.time().strftime(_STRF_NEW)
    else:  # cover gap btn the _DT_LEGACYFMT1/_DT_LEGACYFMT2
        raise ValueError(f"Invalid timestamp {timestamp} entered.")
    filename = 'Injury-Report_' + URLstem_date + '_' + URLstem_time + '.pdf'
    injrep_dlpath = path.join(directorypath, filename)
    return injrep_dlpath


def _pagect_localpdf(filepath: str | PathLike):
    with open(filepath, mode='rb') as injrepfile:
        pdf_reader = PyPDF2.PdfReader(injrepfile)
        pdf_numpgs = len(pdf_reader.pages)
        return pdf_numpgs


_FFILL_COLS = ['Game Date', 'Game Time', 'Matchup', 'Team']
_IDX_PLAYER = _constants.expected_cols.index('Player Name')
_IDX_STATUS = _constants.expected_cols.index('Current Status')
_IDX_REASON = _constants.expected_cols.index('Reason')
_NOT_YET_SUBMITTED = 'NOT YET SUBMITTED'


def _build_injrep(tables: list, numpgs: int, rowgap: float) -> pd.DataFrame:
    """
    Rebuild the report's rows from where each printed line sits on the page. A row's wrapped Reason lines sit
    around its Player Name line, closer together than the gap between rows, so consecutive lines no more than
    rowgap apart belong to one row. A line that cannot be placed raises rather than joining a neighbour's row.
    :param tables: tabula tables read with output_format='json', one per page, in page order
    :param numpgs: number of pages in the pdf
    :param rowgap: largest gap between the tops of consecutive lines of one row (_constants.rowgap_params*)
    """
    if len(tables) != numpgs:
        raise DataValidationError(f"Expected one table per page ({numpgs} pages), got {len(tables)}.")
    pages = [_pagelines(table, pgnum) for pgnum, table in enumerate(tables, start=1)]
    if not pages[0]:
        raise DataValidationError("No text found on page 1.")
    _validate_headers(pd.DataFrame(columns=pages[0][0][1]))

    records = []
    for pgnum, lines in enumerate(pages, start=1):
        rowlines = [line for line in lines if not _is_headerline(line[1])]
        for grpnum, group in enumerate(_group_lines(rowlines, rowgap)):
            if sum(1 for _, texts in group if texts[_IDX_PLAYER]) > 1:
                raise DataValidationError(f"Two player names in one row: {_describe_group(group, pgnum)}")
            record = _group_record(group)
            if record[_IDX_PLAYER] is not None or _is_unsubmitted(record):
                records.append(record)
            elif grpnum == 0 and _is_reasononly(record) and records and records[-1][_IDX_PLAYER] is not None:
                # A row split by a page break: its last lines head the next page
                records[-1] = _append_reason(records[-1], record[_IDX_REASON])
            else:
                raise DataValidationError(f"Line belongs to no row: {_describe_group(group, pgnum)}")

    df_injrep = pd.DataFrame(records, columns=_constants.expected_cols)
    df_injrep[_FFILL_COLS] = df_injrep[_FFILL_COLS].ffill()
    return df_injrep


def _pagelines(table: dict, pgnum: int) -> list:
    """
    A page's printed lines as (top, cell texts), top to bottom; a line with no text is skipped.
    """
    lines = []
    for row in table['data']:
        if len(row) != len(_constants.expected_cols):
            raise DataValidationError(
                f"Page {pgnum}: a line has {len(row)} cells, expected {len(_constants.expected_cols)}.")
        texts = [str(cell['text']).strip() for cell in row]
        tops = [cell['top'] for cell, text in zip(row, texts) if text]
        if tops:
            lines.append((min(tops), texts))
    return sorted(lines, key=lambda line: line[0])


def _group_lines(lines: list, rowgap: float) -> list:
    """
    Split a page's lines into rows wherever the gap between consecutive line tops exceeds rowgap.
    """
    groups = []
    for line in lines:
        if groups and line[0] - groups[-1][-1][0] <= rowgap:
            groups[-1].append(line)
        else:
            groups.append([line])
    return groups


def _group_record(group: list) -> tuple:
    """
    One row's cells: each column's texts, top to bottom, joined by a space (None if the column is empty).
    """
    return tuple(' '.join(texts[idx] for _, texts in group if texts[idx]) or None
                 for idx in range(len(_constants.expected_cols)))


def _is_unsubmitted(record: tuple) -> bool:
    return (record[_IDX_PLAYER] is None and record[_IDX_STATUS] is None and
            str(record[_IDX_REASON]).casefold() == _NOT_YET_SUBMITTED.casefold())


def _is_reasononly(record: tuple) -> bool:
    return record[_IDX_REASON] is not None and all(
        cell is None for idx, cell in enumerate(record) if idx != _IDX_REASON)


def _append_reason(record: tuple, text: str) -> tuple:
    reason = text if record[_IDX_REASON] is None else record[_IDX_REASON] + ' ' + text
    return record[:_IDX_REASON] + (reason,) + record[_IDX_REASON + 1:]


def _describe_group(group: list, pgnum: int) -> str:
    return f"page {pgnum}, " + '; '.join(f"top {top:.1f} {[text for text in texts if text]}" for top, texts in group)


def _normalize_cols(cols) -> list:
    return [re.sub(r'[\W_]+', '', str(colx).strip().lower()) for colx in cols]


def _is_headerline(texts: list) -> bool:
    return _normalize_cols(texts) == _normalize_cols(_constants.expected_cols)


def _validate_headers(df_headpg: pd.DataFrame):
    pg1cols_norm = _normalize_cols(df_headpg.columns)
    expcols_norm = _normalize_cols(_constants.expected_cols)
    if pg1cols_norm == expcols_norm:
        return True
    else:
        unexp_inds = [ind for ind, (x, y) in enumerate(zip(pg1cols_norm, expcols_norm)) if x != y]
        unexp_cols = df_headpg.columns[unexp_inds].tolist()
        raise DataValidationError(f"Incompatible column headers present: {unexp_cols}")

