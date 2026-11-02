"""仅使用 Python 标准库的文件整理工具。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

LOG_DIR = '.file-organizer-logs'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular(path):
    return stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink()


def category(path):
    ext = path.suffix[1:].lower()
    # 限制为安全的文件夹名称，兼容 Windows。
    return 'ext_' + ext if ext and ext.isascii() and ext.isalnum() else 'no_extension'


def available(folder, name, reserved):
    original = Path(name)
    candidate = folder / name
    number = 1
    while os.path.lexists(candidate) or str(candidate).casefold() in reserved:
        candidate = folder / f'{original.stem} ({number}){original.suffix}'
        number += 1
    reserved.add(str(candidate).casefold())
    return candidate


def save(stream, record):
    stream.write(json.dumps(record, ensure_ascii=False) + '\n')
    stream.flush()
    os.fsync(stream.fileno())


def move_exclusive(source, target):
    # 同一目标目录树内使用硬链接再删除原名称：创建目标时绝不覆盖。
    os.link(source, target)
    try:
        source.unlink()
    except OSError:
        target.unlink()
        raise


def organize(folder, apply=False):
    folder = Path(folder).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('目标必须是文件夹')
    reserved = set()
    plan = []
    for source in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
        if regular(source):
            destination_dir = folder / category(source)
            if destination_dir.is_symlink() or (destination_dir.exists() and not destination_dir.is_dir()):
                raise ValueError(f'分类目录不可用：{destination_dir}')
            target = available(destination_dir, source.name, reserved)
            plan.append((source, target))
            print(f'{source.name} -> {target.relative_to(folder)}')
    if not apply:
        print(f'预览：共 {len(plan)} 个文件；传入 --apply 才会移动。')
        return None
    if not plan:
        print('没有需要整理的文件。')
        return None
    logs = folder / LOG_DIR
    if logs.is_symlink():
        raise ValueError('日志目录不能是符号链接')
    logs.mkdir(exist_ok=True)
    logfile = logs / (uuid.uuid4().hex + '.jsonl')
    print(f'日志：{logfile}')
    with logfile.open('x', encoding='utf-8') as stream:
        save(stream, {'version': 1, 'root': str(folder)})
        for source, target in plan:
            target.parent.mkdir(exist_ok=True)
            if target.parent.is_symlink():
                raise ValueError('分类目录不能是符号链接')
            # 先落盘记录；即使中途退出，也能用日志恢复已完成的移动。
            save(stream, {'source': source.name, 'target': target.relative_to(folder).as_posix(), 'sha256': digest(source)})
            move_exclusive(source, target)
    print(f'已移动 {len(plan)} 个文件。')
    return logfile


def undo(logfile, apply=False):
    with Path(logfile).open(encoding='utf-8') as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if not rows or rows[0].get('version') != 1:
        raise ValueError('不支持的日志格式')
    folder = Path(rows[0]['root']).resolve(strict=True)
    count = 0
    for row in reversed(rows[1:]):
        src_rel, dst_rel = Path(row['source']), Path(row['target'])
        if src_rel.is_absolute() or len(src_rel.parts) != 1 or src_rel.name in ('.', '..'):
            raise ValueError('日志包含不安全的源路径')
        if dst_rel.is_absolute() or len(dst_rel.parts) != 2 or '..' in dst_rel.parts:
            raise ValueError('日志包含不安全的目标路径')
        source, target = folder / src_rel, folder / dst_rel
        if target.parent.is_symlink() or not target.resolve().is_relative_to(folder):
            raise ValueError('日志目标超出原文件夹')
        if os.path.lexists(source):
            print(f'跳过（原位置已存在，或已经撤销）：{source.name}')
            continue
        if not target.exists() or not regular(target):
            print(f'跳过（目标缺失或不是普通文件）：{target}')
            continue
        if digest(target) != row['sha256']:
            print(f'跳过（整理后内容已变化）：{target}')
            continue
        print(f'撤销：{dst_rel} -> {src_rel}')
        if apply:
            move_exclusive(target, source)
        count += 1
    print(f'{"已撤销" if apply else "撤销预览"}：{count} 个文件。')
    return count


def main():
    parser = argparse.ArgumentParser(description='按扩展名整理第一层普通文件，默认仅预览。')
    parser.add_argument('folder', nargs='?', help='要整理的文件夹')
    parser.add_argument('--apply', action='store_true', help='实际执行移动或撤销')
    parser.add_argument('--undo', metavar='LOG', help='根据指定 JSONL 日志撤销')
    args = parser.parse_args()
    if bool(args.folder) == bool(args.undo):
        parser.error('请指定目标文件夹，或 --undo 日志，两者只能选一个')
    try:
        if args.undo:
            undo(args.undo, args.apply)
        else:
            organize(args.folder, args.apply)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'操作失败：{exc}\n')


if __name__ == '__main__':
    main()
