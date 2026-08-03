import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('APP_ENV', 'test')
os.environ.setdefault('APP_URL', 'http://testserver')
os.environ.setdefault('COOKIE_SECURE', 'false')
os.environ.setdefault('SUPABASE_URL', 'https://example.supabase.co')
os.environ.setdefault('SUPABASE_SERVICE_KEY', 'test-service-key')
