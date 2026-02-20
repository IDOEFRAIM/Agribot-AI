"""Fix updatedAt columns: server_default -> default for Prisma compatibility."""
import pathlib

p = pathlib.Path("backend/services/models.py")
content = p.read_text(encoding="utf-8")

old = 'Column("updatedAt", DateTime(timezone=True), server_default=func.now(), onupdate=func.now())'
new = 'Column("updatedAt", DateTime(timezone=True), default=func.now(), onupdate=func.now())'

count = content.count(old)
content = content.replace(old, new)
p.write_text(content, encoding="utf-8")
print(f"Replaced {count} occurrences of updatedAt server_default -> default")
