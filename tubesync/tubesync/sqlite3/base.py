import re
from django.db.backends.sqlite3 import base


class DatabaseWrapper(base.DatabaseWrapper):

    def _start_transaction_under_autocommit(self):
        conn_params = self.get_connection_params()
        transaction_modes = frozenset(["DEFERRED", "EXCLUSIVE", "IMMEDIATE"])

        sql_statement = "BEGIN TRANSACTION"
        if "transaction_mode" in conn_params:
            tm = str(conn_params["transaction_mode"]).upper().strip()
            if tm in transaction_modes:
                sql_statement = f"BEGIN {tm} TRANSACTION"
        self.cursor().execute(sql_statement)


    def init_connection_state(self):
        conn_params = self.get_connection_params()
        if "init_command" in conn_params:
            ic = str(conn_params["init_command"])
            cmds = ic.split(';')
            with self.cursor() as cursor:
                for init_cmd in cmds:
                    cursor.execute(init_cmd.strip())


    def _remove_invalid_keyword_argument(self, params):
        try:
            prog = re.compile(r"^(?P<quote>['])(?P<key>[^']+)(?P=quote) is an invalid keyword argument for Connection\(\)$")
            match = prog.match(e.args[0])

        if match:
            key = match.group('key')
            try:
                # remove the invalid keyword argument
                del params[key]
            return True

        return False


    def get_new_connection(self, conn_params):
        filter_map = {
            "transaction_mode": ("isolation_level", "DEFERRED"),
        }
        filtered_params = {k: v for (k,v) in conn_params.items() if k not in filter_map}
        filtered_params.update({v[0]: conn_params.get(k, v[1]) for (k,v) in filter_map.items()})

        attempt = 0
        connection = None
        tries = len(filtered_params)
        while connection is None and attempt < tries:
            attempt += 1
            try:
                connection = super().get_new_connection(filtered_params)
            except TypeError as e:
                if not self._remove_invalid_keyword_argument(filtered_params):
                    # This isn't a TypeError we can handle
                    raise e
        return connection

