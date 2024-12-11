from django.db.backends.sqlite3 import base


class DatabaseWrapper(base.DatabaseWrapper):

    def _start_transaction_under_autocommit(self):
        conn_params = self.get_connection_params()
        if "transaction_mode" not in conn_params:
            self.cursor().execute("BEGIN TRANSACTION")
        else:
            tm = str(conn_params["transaction_mode"]).upper().strip()
            transaction_modes = frozenset(["DEFERRED", "EXCLUSIVE", "IMMEDIATE"])
            if tm in transaction_modes:
                self.cursor().execute(f"BEGIN {tm} TRANSACTION")
            else:
                self.cursor().execute("BEGIN TRANSACTION")


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
        super().get_new_connection(filtered_params)


