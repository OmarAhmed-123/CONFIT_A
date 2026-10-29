-- Runs once on first container start (docker-entrypoint-initdb.d).
-- confit_test  : used by pytest when CONFIT_TEST_DB_URL points at it (tables are
--                created/dropped by the test fixtures).
-- confit_bench : throw-away database for scripts/load/stylist_load.py runs.
CREATE DATABASE confit_test  OWNER confit ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8';
CREATE DATABASE confit_bench OWNER confit ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8';
