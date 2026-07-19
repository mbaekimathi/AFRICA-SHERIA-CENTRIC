import pymysql

# Django 6 checks mysqlclient >= 2.2.1; PyMySQL works as a drop-in with this shim.
pymysql.version_info = (2, 2, 1, "final", 0)
pymysql.install_as_MySQLdb()
