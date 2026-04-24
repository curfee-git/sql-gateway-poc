-- MIT License
--
-- Copyright (c) 2026 Philipp Höllinger
--
-- Permission is hereby granted, free of charge, to any person obtaining a copy
-- of this software and associated documentation files (the "Software"), to deal
-- in the Software without restriction, including without limitation the rights
-- to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
-- copies of the Software, and to permit persons to whom the Software is
-- furnished to do so, subject to the following conditions:
--
-- The above copyright notice and this permission notice shall be included in
-- all copies or substantial portions of the Software.
--
-- THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
-- IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
-- FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
-- AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
-- LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
-- OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
-- THE SOFTWARE.

-- ===========================================================================
-- Demo schema. Every identifier is double-quoted so reserved words like
-- "user", "order", "group", "type", "analyse", "check", "grant", "table" stay
-- legal regardless of Postgres version. Quote once, forget about it.
-- ===========================================================================

-- -----------------------
-- Users: identity + PII.
-- -----------------------
CREATE TABLE IF NOT EXISTS "users" (
    "id"             SERIAL PRIMARY KEY,
    "email"          TEXT NOT NULL UNIQUE,
    "name"           TEXT NOT NULL,
    "password_hash"  TEXT NOT NULL,
    "api_key"        TEXT,
    "phone"          TEXT,
    "date_of_birth"  DATE,
    "ssn"            TEXT,
    "user"           TEXT,
    "group"          TEXT,
    "created_at"     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------
-- Addresses: billing / shipping per user.
-- -----------------------
CREATE TABLE IF NOT EXISTS "addresses" (
    "id"           SERIAL PRIMARY KEY,
    "user_id"      INT NOT NULL REFERENCES "users" ("id"),
    "kind"         TEXT NOT NULL,
    "street"       TEXT NOT NULL,
    "city"         TEXT NOT NULL,
    "postal_code"  TEXT NOT NULL,
    "country"      TEXT NOT NULL,
    "created_at"   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------
-- Products: public catalog.
-- -----------------------
CREATE TABLE IF NOT EXISTS "products" (
    "id"           SERIAL PRIMARY KEY,
    "sku"          TEXT NOT NULL UNIQUE,
    "name"         TEXT NOT NULL,
    "description"  TEXT,
    "category"     TEXT NOT NULL,
    "price_cents"  INT NOT NULL,
    "stock"        INT NOT NULL DEFAULT 0,
    "created_at"   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------
-- Orders: header + shipping address link.
-- -----------------------
CREATE TABLE IF NOT EXISTS "orders" (
    "id"                   SERIAL PRIMARY KEY,
    "user_id"              INT NOT NULL REFERENCES "users" ("id"),
    "amount"               NUMERIC(10, 2) NOT NULL,
    "status"               TEXT NOT NULL DEFAULT 'pending',
    "shipping_address_id"  INT REFERENCES "addresses" ("id"),
    "order"                TEXT,
    "type"                 TEXT,
    "analyse"              TEXT,
    "created_at"           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------
-- Order items: line items per order.
-- -----------------------
CREATE TABLE IF NOT EXISTS "order_items" (
    "id"                SERIAL PRIMARY KEY,
    "order_id"          INT NOT NULL REFERENCES "orders" ("id"),
    "product_id"        INT NOT NULL REFERENCES "products" ("id"),
    "quantity"          INT NOT NULL,
    "unit_price_cents"  INT NOT NULL
);

-- -----------------------
-- Payments: card last four and CVV hash are sensitive.
-- -----------------------
CREATE TABLE IF NOT EXISTS "payments" (
    "id"              SERIAL PRIMARY KEY,
    "order_id"        INT NOT NULL REFERENCES "orders" ("id"),
    "amount"          NUMERIC(10, 2) NOT NULL,
    "method"          TEXT NOT NULL,
    "card_last_four"  TEXT,
    "cvv_hash"        TEXT,
    "transaction_id"  TEXT NOT NULL UNIQUE,
    "created_at"      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------
-- Sessions: bearer tokens. Off-limits to agent_rw.
-- -----------------------
CREATE TABLE IF NOT EXISTS "sessions" (
    "id"             SERIAL PRIMARY KEY,
    "user_id"        INT NOT NULL REFERENCES "users" ("id"),
    "session_token"  TEXT NOT NULL UNIQUE,
    "expires_at"     TIMESTAMPTZ NOT NULL,
    "ip_address"     TEXT,
    "user_agent"     TEXT,
    "created_at"     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------
-- API tokens: also off-limits.
-- -----------------------
CREATE TABLE IF NOT EXISTS "api_tokens" (
    "id"            SERIAL PRIMARY KEY,
    "user_id"       INT NOT NULL REFERENCES "users" ("id"),
    "label"         TEXT NOT NULL,
    "token_hash"    TEXT NOT NULL,
    "scopes"        TEXT NOT NULL,
    "last_used_at"  TIMESTAMPTZ,
    "created_at"    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------
-- Activity log: business events. Agent can INSERT, never SELECT.
-- -----------------------
CREATE TABLE IF NOT EXISTS "activity_log" (
    "id"          SERIAL PRIMARY KEY,
    "user_id"     INT REFERENCES "users" ("id"),
    "event_type"  TEXT NOT NULL,
    "payload"     JSONB,
    "created_at"  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ===========================================================================
-- Seed data. Realistic European / American mix, enough rows for multi-joins
-- and aggregations.
-- ===========================================================================

INSERT INTO "users"
    ("email", "name", "password_hash", "api_key", "phone", "date_of_birth", "ssn")
VALUES
    ('alice@example.com',   'Alice Schmidt',    '$2b$12$aliceHashXxxxxxxxxx',   'sk_live_alice_9f3e', '+491701234567', '1985-03-15', '123-45-6789'),
    ('bob@example.com',     'Bob Müller',       '$2b$12$bobHashXxxxxxxxxxxx',   'sk_live_bob_4a21',   '+491702345678', '1990-07-22', '234-56-7890'),
    ('carol@example.com',   'Carol García',     '$2b$12$carolHashXxxxxxxxxxx',  'sk_live_carol_7d88', '+34600123456',  '1988-11-03', '345-67-8901'),
    ('daniel@example.com',  'Daniel Novak',     '$2b$12$danielHashXxxxxxxxxx',  'sk_live_dan_22ce',   '+420776112233', '1992-02-19', '456-78-9012'),
    ('elena@example.com',   'Elena Bianchi',    '$2b$12$elenaHashXxxxxxxxxxx',  'sk_live_ele_ff00',   '+393351234567', '1987-09-30', '567-89-0123'),
    ('fabian@example.com',  'Fabian Andersson', '$2b$12$fabianHashXxxxxxxxxx',  'sk_live_fab_8800',   '+46701234567',  '1995-12-11', '678-90-1234'),
    ('gabi@example.com',    'Gabi Horvath',     '$2b$12$gabiHashXxxxxxxxxxxx',  'sk_live_gab_3311',   '+43660123456',  '1983-05-04', '789-01-2345'),
    ('henry@example.com',   'Henry O''Brien',   '$2b$12$henryHashXxxxxxxxxxx',  'sk_live_hen_7722',   '+353861234567', '1991-08-17', '890-12-3456'),
    ('isabel@example.com',  'Isabel Lopez',     '$2b$12$isabelHashXxxxxxxxxx',  'sk_live_isa_1199',   '+34690876543',  '1994-04-25', '901-23-4567'),
    ('jan@example.com',     'Jan Kowalski',     '$2b$12$janHashXxxxxxxxxxxxx',  'sk_live_jan_ddee',   '+48501234567',  '1986-10-08', '012-34-5678'),
    ('karen@example.com',   'Karen Chen',       '$2b$12$karenHashXxxxxxxxxxx',  'sk_live_kar_aabb',   '+16505551234',  '1989-06-14', '102-34-5678'),
    ('leo@example.com',     'Leo van Dijk',     '$2b$12$leoHashXxxxxxxxxxxxx',  'sk_live_leo_cc44',   '+31612345678',  '1993-01-28', '203-45-6789'),
    ('maja@example.com',    'Maja Berg',        '$2b$12$majaHashXxxxxxxxxxxx',  'sk_live_maj_5577',   '+4712345678',   '1984-12-02', '304-56-7890'),
    ('niko@example.com',    'Niko Papadopoulos','$2b$12$nikoHashXxxxxxxxxxxx',  'sk_live_nik_9922',   '+306912345678', '1982-07-09', '405-67-8901'),
    ('olga@example.com',    'Olga Petrov',      '$2b$12$olgaHashXxxxxxxxxxxx',  'sk_live_olg_ccdd',   '+48602112233',  '1996-03-21', '506-78-9012')
ON CONFLICT DO NOTHING;

INSERT INTO "addresses"
    ("user_id", "kind", "street", "city", "postal_code", "country")
VALUES
    (1, 'shipping', 'Hauptstrasse 12',    'Berlin',     '10115', 'DE'),
    (1, 'billing',  'Hauptstrasse 12',    'Berlin',     '10115', 'DE'),
    (2, 'shipping', 'Ludwigstrasse 48',   'München',    '80539', 'DE'),
    (3, 'shipping', 'Calle Mayor 23',     'Madrid',     '28013', 'ES'),
    (4, 'shipping', 'Wenceslas Square 1', 'Praha',      '11000', 'CZ'),
    (5, 'shipping', 'Via Roma 55',        'Milano',     '20121', 'IT'),
    (6, 'shipping', 'Drottninggatan 2',   'Stockholm',  '11151', 'SE'),
    (7, 'shipping', 'Ringstrasse 7',      'Wien',       '1010',  'AT'),
    (8, 'shipping', 'Grafton Street 9',   'Dublin',     'D02',   'IE'),
    (9, 'shipping', 'Calle Serrano 88',   'Barcelona',  '08010', 'ES'),
    (10, 'shipping','ul. Marszalkowska 3','Warszawa',   '00001', 'PL'),
    (11, 'shipping','Market Street 100',  'San Jose',   '95113', 'US'),
    (12, 'shipping','Keizersgracht 12',   'Amsterdam',  '1015',  'NL'),
    (13, 'shipping','Karl Johans gate 4', 'Oslo',       '0154',  'NO'),
    (14, 'shipping','Syntagma Square 1',  'Athens',     '10563', 'GR'),
    (15, 'shipping','ul. Piotrkowska 12', 'Lodz',       '90406', 'PL')
ON CONFLICT DO NOTHING;

INSERT INTO "products"
    ("sku", "name", "description", "category", "price_cents", "stock")
VALUES
    ('BK-1001', 'Clean Architecture',         'Software design book by R. C. Martin',  'Books',       3499,  42),
    ('BK-1002', 'Designing Data-Intensive Apps','Kleppmann''s classic',                  'Books',       4499,  30),
    ('BK-1003', 'The Pragmatic Programmer',   '20th anniversary edition',                'Books',       3299,  55),
    ('EL-2001', 'Mechanical Keyboard V2',     '75 percent layout, hot-swap',             'Electronics', 15900, 12),
    ('EL-2002', 'Studio Monitor Headphones',  'Open-back, 32 ohm',                       'Electronics', 24900, 8),
    ('EL-2003', '4K External Monitor',        '27 inch IPS',                             'Electronics', 49900, 5),
    ('EL-2004', 'USB-C Dock',                 '11-in-1 hub',                             'Electronics', 7900,  20),
    ('HM-3001', 'Espresso Machine Pro',       'Dual boiler, PID',                        'Home',        89900, 3),
    ('HM-3002', 'Coffee Grinder',             'Flat burr, stepless',                     'Home',        19900, 15),
    ('HM-3003', 'Kettle 1.7L',                'Variable temperature',                    'Home',        8900,  25),
    ('SP-4001', 'Running Shoes Road',         'Neutral, 10mm drop',                      'Sports',      13500, 18),
    ('SP-4002', 'Yoga Mat 6mm',               'Natural rubber',                          'Sports',      4900,  40),
    ('SP-4003', 'Foam Roller',                'High density',                            'Sports',      2900,  60),
    ('ST-5001', 'Leather Notebook A5',        'Dotted, 200 pages',                       'Stationery',  2900,  80),
    ('ST-5002', 'Fountain Pen Classic',       'Medium nib',                              'Stationery',  6900,  35),
    ('FD-6001', 'Olive Oil 500ml',            'Single estate, Puglia',                   'Food',        1800,  120),
    ('FD-6002', 'Balsamic Vinegar',           'Aged 12 years',                           'Food',        2400,  70),
    ('FD-6003', 'Dark Chocolate 85%',         'Ecuadorian cacao',                        'Food',        690,   200),
    ('CL-7001', 'Merino Sweater',             'Medium, charcoal',                        'Clothing',    8900,  22),
    ('CL-7002', 'Linen Shirt',                'Large, natural',                          'Clothing',    6900,  18)
ON CONFLICT DO NOTHING;

INSERT INTO "orders"
    ("user_id", "amount", "status", "shipping_address_id", "created_at")
VALUES
    (1,  64.98,  'delivered',  1,  NOW() - INTERVAL '40 days'),
    (1,  249.00, 'delivered',  1,  NOW() - INTERVAL '30 days'),
    (2,  32.99,  'shipped',    3,  NOW() - INTERVAL '7 days'),
    (2,  499.00, 'paid',       3,  NOW() - INTERVAL '3 days'),
    (3,  159.00, 'pending',    4,  NOW() - INTERVAL '1 day'),
    (4,  25.00,  'cancelled',  5,  NOW() - INTERVAL '15 days'),
    (5,  89.00,  'delivered',  6,  NOW() - INTERVAL '22 days'),
    (5,  149.00, 'shipped',    6,  NOW() - INTERVAL '5 days'),
    (6,  899.00, 'pending',    7,  NOW() - INTERVAL '1 hour'),
    (7,  29.00,  'delivered',  8,  NOW() - INTERVAL '60 days'),
    (8,  79.00,  'refunded',   9,  NOW() - INTERVAL '20 days'),
    (9,  48.00,  'delivered',  10, NOW() - INTERVAL '12 days'),
    (10, 199.00, 'shipped',    11, NOW() - INTERVAL '2 days'),
    (11, 69.00,  'paid',       12, NOW() - INTERVAL '4 days'),
    (12, 23.00,  'delivered',  13, NOW() - INTERVAL '35 days'),
    (13, 135.00, 'pending',    14, NOW() - INTERVAL '6 hours'),
    (14, 58.00,  'shipped',    15, NOW() - INTERVAL '8 days'),
    (15, 179.00, 'delivered',  16, NOW() - INTERVAL '45 days')
ON CONFLICT DO NOTHING;

INSERT INTO "order_items"
    ("order_id", "product_id", "quantity", "unit_price_cents")
VALUES
    (1,  1, 1, 3499),
    (1,  14, 1, 2900),
    (2,  6, 1, 49900),
    (3,  17, 1, 2400),
    (3,  18, 1, 690),
    (4,  8, 1, 89900),
    (5,  4, 1, 15900),
    (6,  15, 1, 2500),
    (7,  5, 1, 24900),
    (7,  7, 1, 7900),
    (8,  3, 1, 3299),
    (8,  2, 1, 4499),
    (8,  14, 2, 2900),
    (9,  8, 1, 89900),
    (10, 1, 1, 2900),
    (11, 11, 1, 13500),
    (12, 16, 1, 1800),
    (13, 20, 1, 6900),
    (14, 19, 1, 8900),
    (15, 13, 1, 2900),
    (16, 6, 1, 49900),
    (17, 4, 1, 15900)
ON CONFLICT DO NOTHING;

INSERT INTO "payments"
    ("order_id", "amount", "method", "card_last_four", "cvv_hash", "transaction_id")
VALUES
    (1,  64.98,  'card',   '4242', 'hashcvv1xxxxxxxxxxxx',  'txn_20260301_0001'),
    (2,  249.00, 'card',   '1111', 'hashcvv2xxxxxxxxxxxx',  'txn_20260311_0002'),
    (3,  32.99,  'sepa',   NULL,   NULL,                     'txn_20260404_0003'),
    (4,  499.00, 'card',   '9876', 'hashcvv3xxxxxxxxxxxx',  'txn_20260408_0004'),
    (5,  159.00, 'paypal', NULL,   NULL,                     'txn_20260410_0005'),
    (7,  89.00,  'card',   '0007', 'hashcvv4xxxxxxxxxxxx',  'txn_20260319_0006'),
    (8,  149.00, 'card',   '5678', 'hashcvv5xxxxxxxxxxxx',  'txn_20260406_0007'),
    (10, 29.00,  'sepa',   NULL,   NULL,                     'txn_20260202_0008'),
    (12, 48.00,  'paypal', NULL,   NULL,                     'txn_20260329_0009'),
    (13, 199.00, 'card',   '3141', 'hashcvv6xxxxxxxxxxxx',  'txn_20260409_0010'),
    (14, 69.00,  'card',   '2718', 'hashcvv7xxxxxxxxxxxx',  'txn_20260407_0011'),
    (17, 58.00,  'sepa',   NULL,   NULL,                     'txn_20260403_0012'),
    (18, 179.00, 'card',   '8080', 'hashcvv8xxxxxxxxxxxx',  'txn_20260227_0013')
ON CONFLICT DO NOTHING;

INSERT INTO "sessions"
    ("user_id", "session_token", "expires_at", "ip_address", "user_agent")
VALUES
    (1, 'sess_alice_secret_tok_1_xxx',  NOW() + INTERVAL '1 day',  '203.0.113.10', 'Mozilla/5.0 (Macintosh)'),
    (2, 'sess_bob_secret_tok_2_xxxxx',  NOW() + INTERVAL '1 day',  '198.51.100.5', 'Mozilla/5.0 (Windows NT 10.0)'),
    (3, 'sess_carol_secret_tok_3_xxx',  NOW() + INTERVAL '2 days', '203.0.113.22', 'Mozilla/5.0 (Linux; Android)'),
    (5, 'sess_elena_secret_tok_4_xxx',  NOW() + INTERVAL '1 day',  '192.0.2.7',    'Mozilla/5.0 (iPhone)'),
    (11, 'sess_karen_secret_tok_5_xxx', NOW() + INTERVAL '3 days', '203.0.113.45', 'Mozilla/5.0 (X11; Linux x86_64)')
ON CONFLICT DO NOTHING;

INSERT INTO "api_tokens"
    ("user_id", "label", "token_hash", "scopes")
VALUES
    (1, 'Alice CI token',    'sha256:abcdef0123456789aliceapitokenhash1', 'read:orders,write:orders'),
    (2, 'Bob mobile app',    'sha256:bobmobileapitokenhashhhhhhhhhhhh',   'read:orders'),
    (5, 'Elena integration', 'sha256:elenaintegrationapitokenhashhhhh',   'read:products,read:orders'),
    (11, 'Karen admin CLI',  'sha256:karenadmincliapitokenhashxxxxxxxx',  'read:orders,write:orders,read:users')
ON CONFLICT DO NOTHING;

INSERT INTO "activity_log"
    ("user_id", "event_type", "payload")
VALUES
    (1, 'user.login',         '{"ip":"203.0.113.10"}'::jsonb),
    (1, 'order.placed',       '{"order_id":1,"amount":64.98}'::jsonb),
    (2, 'user.login',         '{"ip":"198.51.100.5"}'::jsonb),
    (3, 'user.password_reset','{"method":"email"}'::jsonb),
    (5, 'order.shipped',      '{"order_id":8}'::jsonb)
ON CONFLICT DO NOTHING;

-- ===========================================================================
-- Agent role. Structural boundary: even if Layer 1 lets a DROP through, this
-- role cannot execute it. The decision lives in the permissions, not in hope.
-- ===========================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_rw') THEN
        CREATE ROLE agent_rw LOGIN PASSWORD 'agent_pw';
    END IF;
END $$;

-- Start from zero.
REVOKE ALL ON SCHEMA public                  FROM agent_rw;
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM agent_rw;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM agent_rw;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM agent_rw;

-- Use the schema, but no CREATE in it.
GRANT USAGE ON SCHEMA public TO agent_rw;

-- ---------------------------------------------------------------------------
-- users: column-level SELECT. api_key, password_hash, ssn, date_of_birth are
-- unreachable. INSERT/UPDATE on password_hash IS allowed (for writes), which
-- is why the scrubber redacts password_hash literals in the log.
-- ---------------------------------------------------------------------------
GRANT SELECT ("id", "email", "name", "phone", "user", "group", "created_at")
    ON "users" TO agent_rw;
GRANT INSERT ("email", "name", "password_hash", "phone", "date_of_birth")
    ON "users" TO agent_rw;
GRANT UPDATE ("email", "name", "phone", "password_hash")
    ON "users" TO agent_rw;

-- ---------------------------------------------------------------------------
-- addresses: full DML. Not sensitive.
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON "addresses" TO agent_rw;

-- ---------------------------------------------------------------------------
-- products: public catalog, read-only for the agent.
-- ---------------------------------------------------------------------------
GRANT SELECT ON "products" TO agent_rw;

-- ---------------------------------------------------------------------------
-- orders: full DML.
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON "orders" TO agent_rw;

-- ---------------------------------------------------------------------------
-- order_items: full DML (the agent needs to add / adjust line items).
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON "order_items" TO agent_rw;

-- ---------------------------------------------------------------------------
-- payments: column-level SELECT only. card_last_four and cvv_hash are
-- unreachable. Agents do not write payments (that happens via a separate
-- admin flow).
-- ---------------------------------------------------------------------------
GRANT SELECT ("id", "order_id", "amount", "method", "transaction_id", "created_at")
    ON "payments" TO agent_rw;

-- ---------------------------------------------------------------------------
-- sessions: no permissions at all. SELECT/INSERT/UPDATE/DELETE all return
-- permission denied for table. Even SELECT session_token never resolves.
-- ---------------------------------------------------------------------------
-- (intentionally blank)

-- ---------------------------------------------------------------------------
-- api_tokens: no permissions at all. Same as sessions.
-- ---------------------------------------------------------------------------
-- (intentionally blank)

-- ---------------------------------------------------------------------------
-- activity_log: INSERT only. The agent records events, never reads them.
-- ---------------------------------------------------------------------------
GRANT INSERT ON "activity_log" TO agent_rw;

-- SERIAL sequences.
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO agent_rw;

-- Revoke dangerous filesystem / process functions. Defense in depth against
-- the gateway's dangerous-function list.
REVOKE EXECUTE ON FUNCTION pg_read_file(text)                 FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION pg_read_file(text, bigint, bigint) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION pg_ls_dir(text)                    FROM PUBLIC;
