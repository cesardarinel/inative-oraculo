import paramiko
import re
from pathlib import Path

HOST = 'pub400.com'
PORT = 2222
USER = 'C3S41'
PASS = 'matica96'

def ssh_connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    return client

def run_sql(client, sftp, sql):
    # Write sql to file
    sql_path = '/home/C3S41/q.sql'
    out_path = '/home/C3S41/q.out'
    sh_path = '/home/C3S41/q.sh'
    with sftp.open(sql_path, 'w') as f:
        f.write(sql + '\n')
    with sftp.open(sh_path, 'w') as f:
        f.write('#!/bin/sh\n')
        f.write(f'/usr/bin/db2 -S -f {sql_path} > {out_path} 2>&1\n')
    cmd = 'system "QSH CMD(\'chmod +x ' + sh_path + ' && ' + sh_path + '\') "'
    _, stdout, stderr = client.exec_command(cmd)
    stdout.read()
    stderr.read()
    with sftp.open(out_path, 'rb') as f:
        data = f.read()
    txt = data.decode('cp037', 'replace')
    return txt

def parse_pipe_lines(txt, sep=']'):
    rows = []
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith('00001') or line.startswith('---') or 'RECORD(S) SELECTED' in line:
            continue
        # skip headers
        if line.startswith('TABLE_NAME') or line.startswith('COLUMN_NAME') or line.startswith('DATA_TYPE'):
            continue
        # split by sep
        parts = line.split(sep)
        if len(parts) >= 1:
            rows.append(parts)
    return rows

def main():
    client = ssh_connect()
    sftp = client.open_sftp()
    # Get object list
    sql_list = "SELECT TABLE_NAME || '|' || TABLE_TYPE FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA='QSYS2' AND TABLE_TYPE IN ('T','V') ORDER BY TABLE_NAME"
    txt = run_sql(client, sftp, sql_list)
    objs = []
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith('00001') or line.startswith('---') or 'RECORD' in line:
            continue
        if 'TABLE_NAME' in line:
            continue
        # pipe becomes ]
        if ']' in line:
            name, typ = line.split(']', 1)
            objs.append((name.strip(), typ.strip()))
    # Filter tables
    tables = [n for n,t in objs if t=='T']
    views = [n for n,t in objs if t=='V']
    print(f"Found {len(tables)} tables, {len(views)} views")
    # Fetch columns for all tables
    col_sql = "SELECT TABLE_NAME || '|' || COLUMN_NAME || '|' || DATA_TYPE || '|' || COALESCE(CHAR(ABS(LENGTH)),'0') || '|' || COALESCE(CHAR(ABS(NUMERIC_SCALE)),'0') || '|' || IS_NULLABLE FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA='QSYS2' AND TABLE_NAME IN ('" + "','".join(tables[:200]) + "') ORDER BY TABLE_NAME, ORDINAL_POSITION"
    # To avoid too long IN list, process in batches
    batch_size = 50
    cols_by_table = {}
    for i in range(0, len(tables), batch_size):
        batch = tables[i:i+batch_size]
        sql = "SELECT TABLE_NAME || '|' || COLUMN_NAME || '|' || DATA_TYPE || '|' || COALESCE(CHAR(ABS(LENGTH)),'0') || '|' || COALESCE(CHAR(ABS(NUMERIC_SCALE)),'0') || '|' || IS_NULLABLE FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA='QSYS2' AND TABLE_NAME IN ('" + "','".join(batch) + "') ORDER BY TABLE_NAME, ORDINAL_POSITION"
        txt = run_sql(client, sftp, sql)
        for line in txt.splitlines():
            line = line.strip()
            if not line or line.startswith('00001') or line.startswith('---') or 'RECORD' in line:
                continue
            if 'TABLE_NAME' in line:
                continue
            parts = line.split(']')
            if len(parts) >= 6:
                tname = parts[0].strip()
                cname = parts[1].strip()
                dtype = parts[2].strip()
                length = parts[3].strip()
                scale = parts[4].strip()
                nullable = parts[5].strip()
                cols_by_table.setdefault(tname, []).append((cname, dtype, length, scale, nullable))
    # Build DDL
    def map_type(dtype):
        dtype = dtype.upper()
        if dtype in ('VARCHAR','CHAR','CLOB','DBCLOB','VARG'):
            return 'TEXT'
        if dtype in ('VARBIN','BINARY','BLOB'):
            return 'BLOB'
        if dtype in ('DATE','TIME','TIMESTMP'):
            return 'TEXT'
        if dtype in ('INTEGER','SMALLINT','BIGINT'):
            return 'INTEGER'
        if dtype in ('DECIMAL','NUMERIC'):
            return 'NUMERIC'
        if dtype in ('FLOAT','DOUBLE'):
            return 'REAL'
        return 'TEXT'
    ddl_lines = []
    for tname in tables:
        cols = cols_by_table.get(tname, [])
        if not cols:
            continue
        col_defs = []
        for cname, dtype, length, scale, nullable in cols:
            sql_type = map_type(dtype)
            col_defs.append(f'    "{cname}" {sql_type}')
        ddl = f'CREATE TABLE "{tname}" (\n' + ',\n'.join(col_defs) + '\n);'
        ddl_lines.append(ddl)
    # Views placeholders
    for vname in views[:50]:
        ddl_lines.append(f'-- VIEW {vname} definition omitted for brevity')
    # Write sql file
    sql_file = '/mnt/D/proyectos/Personales/iNative-oraculo/catalogo_qsys2.sql'
    with open(sql_file, 'w', encoding='utf-8') as f:
        f.write('-- QSYS2 catalog extracted from pub400.com\n')
        f.write('\n'.join(ddl_lines))
    print(f'Wrote {sql_file}')
    # Create SQLite DB
    import sqlite3
    db_path = '/mnt/D/proyectos/Personales/iNative-oraculo/qsys2_catalog.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for ddl in ddl_lines:
        if ddl.startswith('CREATE TABLE'):
            try:
                cur.execute(ddl)
            except Exception as e:
                print(f'Error executing {ddl[:80]}: {e}')
    conn.commit()
    conn.close()
    print(f'Wrote {db_path}')
    client.close()

if __name__ == '__main__':
    main()
