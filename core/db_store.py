import sqlite3
import os
from typing import Optional, List, Dict


class DBStore:
    def __init__(self, db_path: str = "data/standards.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表"""
        with self._get_conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS parts (
                    part_no TEXT PRIMARY KEY,
                    allowable_vm REAL NOT NULL,
                    safety_factor REAL DEFAULT 1.0,
                    units TEXT DEFAULT 'MPa',
                    name TEXT,
                    notes TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS mapping(
                    map_type TEXT NOT NULL,
                    map_value TEXT NOT NULL,
                    part_no TEXT NOT NULL,
                    PRIMARY KEY (map_type,map_value),
                    FOREIGN KEY (part_no) REFERENCES parts(part_no)
                )
            ''')
            conn.commit()

    def get_next_part_no(self) -> str:
        """返回下一个可用的零件编号（所有数值编号中最大值+1，无数据则返回'1'）"""
        with self._get_conn() as conn:
            rows = conn.execute('SELECT part_no FROM parts').fetchall()
        if not rows:
            return '1'
        max_no = 0
        for r in rows:
            try:
                val = int(r['part_no'])
                if val > max_no:
                    max_no = val
            except (ValueError, TypeError):
                pass
        return '1' if max_no < 1 else str(max_no + 1)

    def renumber_parts(self, ordered_part_nos: List[str]) -> bool:
        """按照给定顺序对所有零件从1开始重新编号，同步更新 mapping 表"""
        conn = self._get_conn()
        conn.execute('PRAGMA foreign_keys = OFF')
        try:
            for i, old_no in enumerate(ordered_part_nos):
                temp = f'__tmp_{i}__'
                conn.execute('UPDATE parts SET part_no=? WHERE part_no=?', (temp, old_no))
                conn.execute('UPDATE mapping SET part_no=? WHERE part_no=?', (temp, old_no))
            for i in range(len(ordered_part_nos)):
                temp = f'__tmp_{i}__'
                conn.execute('UPDATE parts SET part_no=? WHERE part_no=?', (str(i + 1), temp))
                conn.execute('UPDATE mapping SET part_no=? WHERE part_no=?', (str(i + 1), temp))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute('PRAGMA foreign_keys = ON')
            conn.close()
        return True

    def get_all_parts(self) -> List[Dict]:
        """获取所有零件标准"""
        with self._get_conn() as conn:
            rows = conn.execute('SELECT * FROM parts ORDER BY part_no ').fetchall()
            return [dict(r) for r in rows]

    def get_part(self, part_no: str) -> Optional[Dict]:
        """获取单独零件标准"""
        with self._get_conn() as conn:
            row = conn.execute('SELECT * FROM parts WHERE part_no=?', (part_no,)).fetchone()
            return dict(row) if row else None

    def add_part(self, part_no: str, allowable_vm: float, safety_factor: float = 1.0, units: str = 'MPa', name: str = '', notes: str = ''):
        """添加零件标准"""
        try:
            with self._get_conn() as conn:
                conn.execute('''
                    INSERT INTO parts (part_no, allowable_vm, safety_factor, units, name, notes) VALUES (?,?,?,?,?,?)
                ''', (part_no, allowable_vm, safety_factor, units, name, notes))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_part(self, part_no: str, **kwargs) -> bool:
        """更新零件标准"""
        allowed = {'allowable_vm', 'safety_factor', 'units', 'name', 'notes'}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        set_clause = ','.join(f'{k}=?' for k in updates)
        values = list(updates.values()) + [part_no]
        with self._get_conn() as conn:
            conn.execute(f'UPDATE parts SET {set_clause} WHERE part_no=?', values)
            conn.commit()
        return True

    def delete_part(self, part_no: str) -> bool:
        with self._get_conn() as conn:
            conn.execute('DELETE FROM mapping WHERE part_no=?', (part_no,))
            conn.execute('DELETE FROM parts WHERE part_no=?', (part_no,))
            conn.commit()
        return True

    """Mapping操作"""

    def get_all_mappings(self) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute('SELECT * FROM mapping ORDER BY map_type,map_value').fetchall()
            return [dict(r) for r in rows]

    def add_mapping(self, map_type: str, map_value: str, part_no: str) -> bool:
        if map_type not in ('component', 'part', 'property'):
            return False
        try:
            with self._get_conn() as conn:
                conn.execute('INSERT INTO mapping VALUES (?,?,?)', (map_type, map_value, part_no))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_mapping(self, map_type: str, map_value: str) -> bool:
        with self._get_conn() as conn:
            conn.execute('DELETE FROM mapping WHERE map_type=? AND map_value=?', (map_type, map_value))
            conn.commit()
        return True

    def find_part_by_tags(self, tags: Dict[str, str]) -> Optional[Dict]:
        priority = ['component', 'part', 'property']
        with self._get_conn() as conn:
            for map_type in priority:
                if map_type in tags and tags[map_type]:
                    row = conn.execute('''
                        SELECT p.* FROM parts p JOIN mapping m ON p.part_no =m.part_no
                        WHERE m.map_type=? AND m.map_value=?
                    ''', (map_type, tags[map_type])).fetchone()
                    if row:
                        return dict(row)
        return None

    def export_parts_csv(self, filepath: str):
        import csv
        parts = self.get_all_parts()
        if not parts:
            return
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=parts[0].keys())
            writer.writeheader()
            writer.writerows(parts)

    def import_parts_csv(self, filepath: str) -> int:
        import csv
        count = 0
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if self.add_part(
                    row['part_no'],
                    float(row['allowable_vm']),
                    float(row.get('safety_factor', 1.0)),
                    row.get('units', 'MPa'),
                    row.get('name', ''),
                    row.get('notes', '')
                ):
                    count += 1
        return count
