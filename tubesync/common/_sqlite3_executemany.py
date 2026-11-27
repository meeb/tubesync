import contextlib
import sqlite3
import time

from collections import deque
from collections.abc import Iterable
from pathlib import Path

from ._batched import batched


def _padded_keys(keys: Iterable[object], size: int) -> Iterable[object]:
    iterator = iter(keys)
    try:
        first_key = next(iterator)
    except StopIteration:
        return

    pending = deque([first_key], maxlen=size)

    for key in iterator:
        if len(pending) == pending.maxlen:
            yield from tuple(pending)
            pending.clear()
        pending.append(key)

    if pending:
        pending.extend(
            first_key for _ in range(pending.maxlen - len(pending))
        )
        yield from tuple(pending)

def execute_many(
    db_path: Path,
    sql_statement: str,
    binding_args: Iterable[object],
    *,
    bindings_per_statement: int = 100,
    needle: str = '{}',
    prefix_binding_args: tuple[object, ...] = (),
    statements_per_transaction: int = 10,
    sleep_seconds: float = 0.1,
) -> int:
    value_error_message = None
    if 1 > bindings_per_statement:
        value_error_message = 'bindings_per_statement'
    elif 1 > statements_per_transaction:
        value_error_message = 'statements_per_transaction'
    if value_error_message:
        value_error_message += ' must be at least 1'
    elif 0 > sleep_seconds:
        value_error_message = 'sleep_seconds must not be negative'
    if value_error_message:
        raise ValueError(value_error_message)

    needle_expression = f' IN ({needle})'
    if 1 != sql_statement.count(needle_expression):
        raise ValueError('sql_statement must contain the IN needle exactly once')

    affected_rows = 0
    placeholders = ', '.join('?' for _ in range(bindings_per_statement))
    statement = sql_statement.replace(
        needle_expression,
        f' IN ({placeholders})',
        count=1,
    )

    statement_batches = batched(
        _padded_keys(binding_args, bindings_per_statement),
        bindings_per_statement,
        strict=True,
    )

    for transaction_index, transaction_batches in enumerate(
        batched(statement_batches, statements_per_transaction, strict=False)
    ):
        if transaction_index and sleep_seconds:
            time.sleep(sleep_seconds)

        with contextlib.closing(
            sqlite3.connect(db_path, isolation_level='IMMEDIATE'),
        ) as connection, connection:
            for batch in transaction_batches:
                with contextlib.closing(
                    connection.execute(statement, prefix_binding_args + batch),
                ) as cursor:
                    if 0 <= cursor.rowcount:
                        affected_rows += cursor.rowcount

    return affected_rows
