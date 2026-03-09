import unittest
import os
import tempfile
from pathlib import Path


class TestCacheDocumentation(unittest.TestCase):
    """Test that verifies cache documentation matches implementation."""
    
    def test_cache_environment_variable_default(self):
        """Verify WEATHER_CACHE_DB_PATH defaults to 'app.db'."""
        # Test the default behavior when env var is not set
        if 'WEATHER_CACHE_DB_PATH' in os.environ:
            original = os.environ['WEATHER_CACHE_DB_PATH']
            del os.environ['WEATHER_CACHE_DB_PATH']
        
        # Import here to avoid caching issues
        import backend.main
        
        # The _cache_database_path function should return Path('app.db')
        result = backend.main._cache_database_path()
        self.assertEqual(str(result), 'app.db')
        
        if 'original' in locals():
            os.environ['WEATHER_CACHE_DB_PATH'] = original
    
    def test_cache_environment_variable_custom(self):
        """Verify WEATHER_CACHE_DB_PATH can be customized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir) / 'custom.db'
            os.environ['WEATHER_CACHE_DB_PATH'] = str(custom_path)
            
            # Import here to avoid caching issues
            import importlib
            import backend.main
            importlib.reload(backend.main)
            
            result = backend.main._cache_database_path()
            self.assertEqual(str(result), str(custom_path))
            
            del os.environ['WEATHER_CACHE_DB_PATH']
    
    def test_cache_ttl_constant(self):
        """Verify cache TTL is 900 seconds (15 minutes)."""
        import backend.main
        self.assertEqual(backend.main.CACHE_TTL_SECONDS, 900)
    
    def test_cache_table_schema_matches_documentation(self):
        """Verify the cache table creation SQL matches documented schema."""
        import backend.main
        import sqlite3
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'
            os.environ['WEATHER_CACHE_DB_PATH'] = str(db_path)
            
            # Import here to avoid caching issues
            import importlib
            importlib.reload(backend.main)
            
            # Create connection to trigger table creation
            conn = backend.main._cache_connection()
            conn.close()
            
            # Verify table structure
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Get table info
                cursor.execute("PRAGMA table_info(weather_cache)")
                columns = cursor.fetchall()
                
                # Check expected columns exist
                column_names = [col[1] for col in columns]
                expected_columns = ['id', 'city_key', 'forecast_range', 'units', 
                                   'status_code', 'payload', 'created_at', 'expires_at']
                
                for col in expected_columns:
                    self.assertIn(col, column_names, f"Column {col} missing from weather_cache table")
                
                # Check UNIQUE constraint
                cursor.execute("PRAGMA index_list(weather_cache)")
                indexes = cursor.fetchall()
                has_unique = False
                for idx in indexes:
                    if idx[2]:  # unique flag
                        cursor.execute(f"PRAGMA index_info({idx[1]})")
                        idx_info = cursor.fetchall()
                        idx_cols = [info[2] for info in idx_info]
                        if set(['city_key', 'forecast_range', 'units']).issubset(set(idx_cols)):
                            has_unique = True
                            break
                
                self.assertTrue(has_unique, "Missing UNIQUE constraint on (city_key, forecast_range, units)")
            
            del os.environ['WEATHER_CACHE_DB_PATH']


if __name__ == '__main__':
    unittest.main()