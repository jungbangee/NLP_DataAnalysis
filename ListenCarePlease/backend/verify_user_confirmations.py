import sys
sys.path.insert(0, '/app')

from app.db.session import SessionLocal
from app.models.user_confirmation import UserConfirmation
from sqlalchemy import inspect

db = SessionLocal()
inspector = inspect(db.bind)

# Check if table exists
tables = inspector.get_table_names()
print('user_confirmations exists:', 'user_confirmations' in tables)

# Get columns
if 'user_confirmations' in tables:
    columns = inspector.get_columns('user_confirmations')
    print('\nColumns:')
    for col in columns:
        print(f"  {col['name']}: {col['type']}")

# Check row count
count = db.query(UserConfirmation).count()
print(f'\nRow count: {count}')

db.close()
