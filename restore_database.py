#!/usr/bin/env python3
"""
数据库恢复脚本
用于从备份文件恢复 PostgreSQL 数据库

使用方法:
    python restore_database.py <备份文件路径> [--drop-existing] [--create-db]
    
示例:
    python restore_database.py backups/db_backup_20240101.sql
    python restore_database.py backups/db_backup_20240101.dump --drop-existing
"""

import sys
import os
import argparse
import subprocess
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings

def parse_database_url(db_url: str) -> dict:
    """解析数据库 URL，提取连接信息"""
    # 格式: postgresql://user:password@host:port/database
    # 或: postgresql+psycopg2://user:password@host:port/database
    db_url = db_url.replace('postgresql+psycopg2://', 'postgresql://')
    db_url = db_url.replace('postgresql://', '')
    
    if '@' in db_url:
        auth, rest = db_url.split('@', 1)
        if ':' in auth:
            user, password = auth.split(':', 1)
        else:
            user = auth
            password = ''
    else:
        user = 'postgres'
        password = ''
        rest = db_url
    
    if '/' in rest:
        host_port, database = rest.rsplit('/', 1)
    else:
        host_port = rest
        database = 'postgres'
    
    if ':' in host_port:
        host, port = host_port.split(':', 1)
        port = int(port)
    else:
        host = host_port
        port = 5432
    
    return {
        'host': host,
        'port': port,
        'user': user,
        'password': password,
        'database': database
    }

def check_pg_restore():
    """检查 pg_restore 是否可用"""
    try:
        result = subprocess.run(
            ['pg_restore', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def check_psql():
    """检查 psql 是否可用"""
    try:
        result = subprocess.run(
            ['psql', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def detect_backup_format(backup_path: str) -> str:
    """检测备份文件格式"""
    # 检查文件扩展名
    ext = Path(backup_path).suffix.lower()
    if ext == '.dump' or ext == '.backup':
        return 'custom'
    elif ext == '.tar':
        return 'tar'
    elif ext == '.sql' or ext == '.sql.gz':
        return 'plain'
    else:
        # 尝试读取文件头来判断
        try:
            with open(backup_path, 'rb') as f:
                header = f.read(5)
                if header == b'PGDMP':
                    return 'custom'
                elif header.startswith(b'--'):
                    return 'plain'
        except:
            pass
        return 'unknown'

def drop_database(db_info: dict, env: dict):
    """删除数据库"""
    print("正在删除现有数据库...")
    
    # 连接到 postgres 数据库来删除目标数据库
    cmd = [
        'psql',
        '-h', db_info['host'],
        '-p', str(db_info['port']),
        '-U', db_info['user'],
        '-d', 'postgres',  # 连接到默认数据库
        '-c', f'DROP DATABASE IF EXISTS "{db_info["database"]}";'
    ]
    
    try:
        subprocess.run(cmd, env=env, check=True, capture_output=True)
        print("✅ 数据库已删除")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  警告: 删除数据库失败: {e}")
        return False

def create_database(db_info: dict, env: dict):
    """创建数据库"""
    print("正在创建数据库...")
    
    cmd = [
        'psql',
        '-h', db_info['host'],
        '-p', str(db_info['port']),
        '-U', db_info['user'],
        '-d', 'postgres',  # 连接到默认数据库
        '-c', f'CREATE DATABASE "{db_info["database"]}";'
    ]
    
    try:
        subprocess.run(cmd, env=env, check=True, capture_output=True)
        print("✅ 数据库已创建")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 错误: 创建数据库失败: {e}")
        if e.stderr:
            print(f"   错误信息: {e.stderr.decode()}")
        return False

def drop_all_tables(db_info: dict, env: dict):
    """删除数据库中的所有表（用于完全替换）"""
    print("正在删除所有现有表...")
    
    # 生成删除所有表的 SQL 命令
    # 先删除外键约束，然后删除表
    drop_tables_sql = """
DO $$ 
DECLARE 
    r RECORD;
BEGIN
    -- 删除所有外键约束
    FOR r IN (SELECT conname, conrelid::regclass 
              FROM pg_constraint 
              WHERE contype = 'f' 
              AND connamespace = 'public'::regnamespace) 
    LOOP
        EXECUTE 'ALTER TABLE ' || r.conrelid || ' DROP CONSTRAINT ' || r.conname;
    END LOOP;
    
    -- 删除所有表
    FOR r IN (SELECT tablename 
              FROM pg_tables 
              WHERE schemaname = 'public') 
    LOOP
        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
    
    -- 删除所有序列（如果有）
    FOR r IN (SELECT sequence_name 
              FROM information_schema.sequences 
              WHERE sequence_schema = 'public') 
    LOOP
        EXECUTE 'DROP SEQUENCE IF EXISTS ' || quote_ident(r.sequence_name) || ' CASCADE';
    END LOOP;
END $$;
"""
    
    cmd = [
        'psql',
        '-h', db_info['host'],
        '-p', str(db_info['port']),
        '-U', db_info['user'],
        '-d', db_info['database'],
        '-c', drop_tables_sql
    ]
    
    try:
        result = subprocess.run(
            cmd,
            env=env,
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ 所有表已删除")
        return True
    except subprocess.CalledProcessError as e:
        print(f"⚠️  警告: 删除表时出错: {e}")
        if e.stderr:
            print(f"   错误信息: {e.stderr}")
        # 尝试使用更简单的方法
        return drop_all_tables_simple(db_info, env)

def drop_all_tables_simple(db_info: dict, env: dict):
    """使用简单方法删除所有表（备用方案）"""
    print("尝试使用简单方法删除表...")
    
    # 按依赖顺序删除表
    tables = ['transactions', 'items', 'categories', 'warehouses', 'admin']
    
    for table in tables:
        cmd = [
            'psql',
            '-h', db_info['host'],
            '-p', str(db_info['port']),
            '-U', db_info['user'],
            '-d', db_info['database'],
            '-c', f'DROP TABLE IF EXISTS "{table}" CASCADE;'
        ]
        try:
            subprocess.run(cmd, env=env, check=True, capture_output=True)
        except:
            pass  # 忽略错误，继续删除其他表
    
    print("✅ 表删除完成（可能部分失败）")
    return True

def restore_database(
    backup_path: str,
    drop_existing: bool = False,
    create_db: bool = False
):
    """恢复数据库"""
    # 检查备份文件是否存在
    if not os.path.exists(backup_path):
        print(f"❌ 错误: 备份文件不存在: {backup_path}")
        return False
    
    # 检查工具
    backup_format = detect_backup_format(backup_path)
    
    if backup_format == 'custom' or backup_format == 'tar':
        if not check_pg_restore():
            print("❌ 错误: 未找到 pg_restore 命令")
            print("   请确保 PostgreSQL 客户端工具已安装并在 PATH 中")
            return False
    else:
        if not check_psql():
            print("❌ 错误: 未找到 psql 命令")
            print("   请确保 PostgreSQL 客户端工具已安装并在 PATH 中")
            return False
    
    # 解析数据库 URL
    try:
        db_info = parse_database_url(settings.DATABASE_URL)
    except Exception as e:
        print(f"❌ 错误: 无法解析数据库 URL: {e}")
        return False
    
    # 设置环境变量（密码）
    env = os.environ.copy()
    if db_info['password']:
        env['PGPASSWORD'] = db_info['password']
    
    print(f"\n{'='*60}")
    print("数据库恢复")
    print(f"{'='*60}")
    print(f"备份文件: {backup_path}")
    print(f"格式: {backup_format}")
    print(f"数据库: {db_info['database']}")
    print(f"主机: {db_info['host']}:{db_info['port']}")
    print(f"用户: {db_info['user']}")
    print(f"{'='*60}\n")
    
    # 确认
    if drop_existing:
        confirm = input("⚠️  警告: 将删除现有数据库并重新创建，确认继续？(输入 'yes' 确认): ")
        if confirm.lower() != 'yes':
            print("❌ 操作已取消")
            return False
        
        # 删除数据库
        if not drop_database(db_info, env):
            print("⚠️  继续尝试恢复...")
        
        # 创建数据库
        if not create_database(db_info, env):
            return False
    else:
        # 即使不删除数据库，也要先删除所有表以确保完全替换
        print("\n⚠️  注意: 将删除所有现有表，然后恢复备份数据")
        confirm = input("确认继续？(输入 'yes' 确认): ")
        if confirm.lower() != 'yes':
            print("❌ 操作已取消")
            return False
        
        # 删除所有表
        if not drop_all_tables(db_info, env):
            print("⚠️  继续尝试恢复...")
    
    if create_db:
        # 只创建数据库（如果不存在）
        print("检查数据库是否存在...")
        check_cmd = [
            'psql',
            '-h', db_info['host'],
            '-p', str(db_info['port']),
            '-U', db_info['user'],
            '-d', 'postgres',
            '-tAc', f"SELECT 1 FROM pg_database WHERE datname='{db_info['database']}'"
        ]
        try:
            result = subprocess.run(
                check_cmd,
                env=env,
                check=True,
                capture_output=True,
                text=True
            )
            if not result.stdout.strip():
                # 数据库不存在，创建它
                if not create_database(db_info, env):
                    return False
        except:
            # 如果检查失败，尝试创建
            if not create_database(db_info, env):
                return False
    
    # 执行恢复
    try:
        if backup_format == 'custom' or backup_format == 'tar':
            # 使用 pg_restore
            print("正在恢复数据库（使用 pg_restore）...")
            # 注意：如果已经删除了所有表，--clean 选项可能会导致错误
            # 因为 --clean 会尝试删除不存在的对象
            # 所以如果已经手动删除了表，就不使用 --clean
            cmd = [
                'pg_restore',
                '-h', db_info['host'],
                '-p', str(db_info['port']),
                '-U', db_info['user'],
                '-d', db_info['database'],
                '--verbose',
                '--no-owner',
                '--no-acl',
                backup_path
            ]
            
            result = subprocess.run(
                cmd,
                env=env,
                check=True,
                capture_output=False,
                text=True
            )
        else:
            # 使用 psql 执行 SQL 文件
            print("正在恢复数据库（使用 psql）...")
            cmd = [
                'psql',
                '-h', db_info['host'],
                '-p', str(db_info['port']),
                '-U', db_info['user'],
                '-d', db_info['database'],
                '-f', backup_path
            ]
            
            result = subprocess.run(
                cmd,
                env=env,
                check=True,
                capture_output=False,
                text=True
            )
        
        print(f"\n✅ 恢复成功!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 恢复失败: {e}")
        if e.stderr:
            print(f"   错误信息: {e.stderr}")
        return False
    except Exception as e:
        print(f"\n❌ 恢复失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(description='数据库恢复脚本')
    parser.add_argument(
        'backup_path',
        type=str,
        help='备份文件路径'
    )
    parser.add_argument(
        '--drop-existing',
        action='store_true',
        help='删除现有数据库并重新创建（危险操作）'
    )
    parser.add_argument(
        '--create-db',
        action='store_true',
        help='如果数据库不存在则创建'
    )
    
    args = parser.parse_args()
    
    success = restore_database(
        backup_path=args.backup_path,
        drop_existing=args.drop_existing,
        create_db=args.create_db
    )
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()

