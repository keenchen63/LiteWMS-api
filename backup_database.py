#!/usr/bin/env python3
"""
数据库备份脚本
用于备份 PostgreSQL 数据库

使用方法:
    python backup_database.py [--output <备份文件路径>] [--format <格式>]
    
示例:
    python backup_database.py
    python backup_database.py --output backups/db_backup_20240101.sql
    python backup_database.py --format custom --output backups/db_backup_20240101.dump
"""

import sys
import os
import argparse
import subprocess
from datetime import datetime
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

def check_pg_dump():
    """检查 pg_dump 是否可用"""
    try:
        result = subprocess.run(
            ['pg_dump', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def backup_database(
    output_path: str = None,
    format: str = 'plain',
    compress: bool = False
):
    """备份数据库"""
    # 检查 pg_dump
    if not check_pg_dump():
        print("❌ 错误: 未找到 pg_dump 命令")
        print("   请确保 PostgreSQL 客户端工具已安装并在 PATH 中")
        print("   macOS: brew install postgresql")
        print("   Ubuntu: sudo apt-get install postgresql-client")
        return False
    
    # 解析数据库 URL
    try:
        db_info = parse_database_url(settings.DATABASE_URL)
    except Exception as e:
        print(f"❌ 错误: 无法解析数据库 URL: {e}")
        return False
    
    # 确定输出文件路径
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path(__file__).parent / 'backups'
        backup_dir.mkdir(exist_ok=True)
        
        if format == 'custom':
            output_path = str(backup_dir / f"db_backup_{timestamp}.dump")
        else:
            output_path = str(backup_dir / f"db_backup_{timestamp}.sql")
    else:
        output_path = os.path.abspath(output_path)
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
    
    # 构建 pg_dump 命令
    cmd = ['pg_dump']
    
    # 添加连接参数
    cmd.extend(['-h', db_info['host']])
    cmd.extend(['-p', str(db_info['port'])])
    cmd.extend(['-U', db_info['user']])
    cmd.extend(['-d', db_info['database']])
    
    # 格式选项
    if format == 'custom':
        cmd.append('--format=custom')
        cmd.append('--compress=9')  # 压缩级别 0-9
    elif format == 'directory':
        cmd.append('--format=directory')
    elif format == 'tar':
        cmd.append('--format=tar')
    else:
        # plain 格式
        cmd.append('--format=plain')
        if compress:
            cmd.append('--compress=9')
    
    # 其他选项
    cmd.append('--verbose')  # 详细输出
    cmd.append('--no-owner')  # 不包含所有者信息
    cmd.append('--no-acl')  # 不包含访问权限信息
    
    # 输出文件
    cmd.append('--file=' + output_path)
    
    print(f"\n{'='*60}")
    print("数据库备份")
    print(f"{'='*60}")
    print(f"数据库: {db_info['database']}")
    print(f"主机: {db_info['host']}:{db_info['port']}")
    print(f"用户: {db_info['user']}")
    print(f"格式: {format}")
    print(f"输出: {output_path}")
    print(f"{'='*60}\n")
    
    # 设置环境变量（密码）
    env = os.environ.copy()
    if db_info['password']:
        env['PGPASSWORD'] = db_info['password']
    
    try:
        # 执行备份
        print("正在备份数据库...")
        result = subprocess.run(
            cmd,
            env=env,
            check=True,
            capture_output=False,
            text=True
        )
        
        # 检查文件是否创建
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            file_size_mb = file_size / (1024 * 1024)
            print(f"\n✅ 备份成功!")
            print(f"   文件: {output_path}")
            print(f"   大小: {file_size_mb:.2f} MB")
            return True
        else:
            print(f"\n❌ 备份失败: 输出文件未创建")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 备份失败: {e}")
        if e.stderr:
            print(f"   错误信息: {e.stderr}")
        return False
    except Exception as e:
        print(f"\n❌ 备份失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    parser = argparse.ArgumentParser(description='数据库备份脚本')
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='备份文件输出路径（默认: backups/db_backup_YYYYMMDD_HHMMSS.sql）'
    )
    parser.add_argument(
        '--format', '-f',
        type=str,
        choices=['plain', 'custom', 'directory', 'tar'],
        default='plain',
        help='备份格式: plain (SQL), custom (压缩), directory, tar (默认: plain)'
    )
    parser.add_argument(
        '--compress',
        action='store_true',
        help='对 plain 格式启用压缩（仅用于 plain 格式）'
    )
    
    args = parser.parse_args()
    
    success = backup_database(
        output_path=args.output,
        format=args.format,
        compress=args.compress
    )
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()

