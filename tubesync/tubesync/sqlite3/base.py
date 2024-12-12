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

    
    def get_new_connection(self, conn_params):
        filtered_params = conn_params.copy()
        filtered_params["isolation_level"] = filtered_params.pop("transaction_mode", "DEFERRED")
        _ = filtered_params.pop("init_command", None)
        return super().get_new_connection(filtered_params)


