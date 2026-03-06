-- MuShop Cloud Native Portal - Database Initialization
-- Compatible with both PostgreSQL and Oracle (using standard SQL)

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(200) UNIQUE NOT NULL,
    password_hash VARCHAR(300) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    sku VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    price FLOAT NOT NULL,
    stock INTEGER DEFAULT 0,
    category VARCHAR(100),
    image_url VARCHAR(500),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(200) UNIQUE NOT NULL,
    phone VARCHAR(50),
    company VARCHAR(200),
    industry VARCHAR(100),
    revenue FLOAT DEFAULT 0.0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    total FLOAT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    notes TEXT,
    shipping_address TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price FLOAT NOT NULL
);

CREATE TABLE IF NOT EXISTS cart_items (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    customer_id INTEGER REFERENCES customers(id),
    rating INTEGER NOT NULL,
    comment TEXT,
    author_name VARCHAR(200),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS coupons (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    discount_percent FLOAT DEFAULT 0.0,
    discount_amount FLOAT DEFAULT 0.0,
    is_active BOOLEAN DEFAULT true,
    max_uses INTEGER DEFAULT 100,
    used_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shipments (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    tracking_number VARCHAR(100),
    carrier VARCHAR(100),
    status VARCHAR(50) DEFAULT 'processing',
    origin_region VARCHAR(50),
    destination_region VARCHAR(50),
    weight_kg FLOAT DEFAULT 0.0,
    shipping_cost FLOAT DEFAULT 0.0,
    estimated_delivery TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS warehouses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    region VARCHAR(50) NOT NULL,
    address TEXT,
    capacity INTEGER DEFAULT 10000,
    current_stock INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    campaign_type VARCHAR(50) DEFAULT 'email',
    status VARCHAR(50) DEFAULT 'draft',
    budget FLOAT DEFAULT 0.0,
    spent FLOAT DEFAULT 0.0,
    target_audience TEXT,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER REFERENCES campaigns(id),
    email VARCHAR(200) NOT NULL,
    name VARCHAR(200),
    source VARCHAR(100),
    status VARCHAR(50) DEFAULT 'new',
    score INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS page_views (
    id SERIAL PRIMARY KEY,
    page VARCHAR(200) NOT NULL,
    visitor_ip VARCHAR(50),
    visitor_region VARCHAR(50),
    user_agent VARCHAR(500),
    load_time_ms INTEGER,
    referrer VARCHAR(500),
    session_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(200),
    details TEXT,
    ip_address VARCHAR(50),
    trace_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ── Seed Data ────────────────────────────────────────────────────

INSERT INTO users (username, email, password_hash, role) VALUES
    ('admin', 'admin@mushop.local', '$2b$12$LJ3X5wKv7IfAzGMkVbHDneFQ3KQJXhHjqW/Tq3hXqp6NpXq8vU5Lm', 'admin'),
    ('shopper', 'shopper@mushop.local', '$2b$12$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy', 'user'),
    ('manager', 'manager@mushop.local', '$2b$12$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy', 'manager')
ON CONFLICT DO NOTHING;

INSERT INTO products (name, sku, description, price, stock, category, image_url) VALUES
    ('MuShop Classic Tee', 'TEE-001', 'Classic cotton t-shirt with MuShop logo', 29.99, 500, 'Clothing', '/static/img/tee-classic.png'),
    ('MuShop Hoodie', 'HOD-001', 'Warm hoodie for cloud-native developers', 59.99, 200, 'Clothing', '/static/img/hoodie.png'),
    ('Cloud Socks (3-pack)', 'SOC-001', 'Comfortable socks with cloud patterns', 14.99, 1000, 'Clothing', '/static/img/socks.png'),
    ('DevOps Cap', 'CAP-001', 'Baseball cap for the DevOps lifestyle', 24.99, 300, 'Accessories', '/static/img/cap.png'),
    ('Kubernetes Sticker Pack', 'STK-001', 'Pack of 10 Kubernetes-themed stickers', 9.99, 2000, 'Accessories', '/static/img/stickers.png'),
    ('OCI Mug', 'MUG-001', 'Ceramic mug with Oracle Cloud logo', 19.99, 400, 'Drinkware', '/static/img/mug-oci.png'),
    ('Microservices Mug', 'MUG-002', 'Mug celebrating distributed systems', 19.99, 350, 'Drinkware', '/static/img/mug-micro.png'),
    ('Cloud Native Backpack', 'BAG-001', 'Durable laptop backpack for on-the-go', 79.99, 100, 'Bags', '/static/img/backpack.png'),
    ('Terraform Notebook', 'NTB-001', 'Hardcover notebook for infrastructure planning', 15.99, 600, 'Stationery', '/static/img/notebook.png'),
    ('Docker Whale Plush', 'PLH-001', 'Adorable blue whale plushie', 24.99, 150, 'Toys', '/static/img/whale.png'),
    ('Observability Poster', 'PST-001', 'Wall poster: traces, metrics, and logs', 12.99, 400, 'Decor', '/static/img/poster.png'),
    ('Zero Trust Lanyard', 'LAN-001', 'Security-themed conference lanyard', 7.99, 800, 'Accessories', '/static/img/lanyard.png')
ON CONFLICT DO NOTHING;

INSERT INTO customers (name, email, phone, company, industry, revenue) VALUES
    ('Acme Corp', 'contact@acme.com', '+1-555-0101', 'Acme Corporation', 'Manufacturing', 5200000),
    ('Globex Industries', 'info@globex.com', '+1-555-0102', 'Globex', 'Technology', 12800000),
    ('Initech Solutions', 'sales@initech.com', '+1-555-0103', 'Initech', 'Consulting', 3400000),
    ('Stark Industries', 'tony@stark.com', '+1-555-0105', 'Stark Ind', 'Defense', 89000000),
    ('Wayne Enterprises', 'bruce@wayne.com', '+1-555-0106', 'Wayne Ent', 'Conglomerate', 120000000),
    ('Cyberdyne Systems', 'info@cyberdyne.com', '+1-555-0107', 'Cyberdyne', 'AI/Robotics', 8900000)
ON CONFLICT DO NOTHING;

INSERT INTO orders (customer_id, total, status, shipping_address) VALUES
    (1, 89.97, 'completed', '123 Industrial Way, Springfield'),
    (2, 159.97, 'processing', '456 Tech Park, Silicon Valley'),
    (3, 44.98, 'pending', '789 Consulting Blvd, New York'),
    (4, 79.99, 'shipped', '10880 Malibu Point, CA'),
    (1, 29.99, 'completed', '123 Industrial Way, Springfield'),
    (5, 134.97, 'processing', '1007 Mountain Drive, Gotham')
ON CONFLICT DO NOTHING;

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1, 1, 2, 29.99), (1, 3, 2, 14.99),
    (2, 2, 1, 59.99), (2, 8, 1, 79.99), (2, 6, 1, 19.99),
    (3, 5, 2, 9.99), (3, 9, 1, 15.99), (3, 12, 1, 7.99),
    (4, 8, 1, 79.99),
    (5, 1, 1, 29.99),
    (6, 2, 1, 59.99), (6, 4, 1, 24.99), (6, 10, 2, 24.99)
ON CONFLICT DO NOTHING;

INSERT INTO reviews (product_id, rating, comment, author_name) VALUES
    (1, 5, 'Best t-shirt ever! Super comfortable.', 'CloudFan'),
    (1, 4, 'Nice quality, runs a bit large', 'DevOpsGuru'),
    (2, 5, 'Perfect for those chilly server room visits', 'SRELife'),
    (3, 3, 'Socks are ok, expected more cloud patterns', 'K8sNewbie'),
    (6, 5, 'Great mug! Keeps coffee hot during standups', 'MorningDev'),
    (8, 4, 'Solid backpack, fits 15" laptop perfectly', 'NomadCoder'),
    (10, 5, 'So cute! Sits on my monitor now', 'DockerLover')
ON CONFLICT DO NOTHING;

INSERT INTO coupons (code, discount_percent, discount_amount, is_active, max_uses) VALUES
    ('WELCOME10', 10.0, 0.0, true, 1000),
    ('CLOUD20', 20.0, 0.0, true, 500),
    ('FREESHIP', 0.0, 9.99, true, 200),
    ('VIP50', 50.0, 0.0, true, 10),
    ('EXPIRED', 15.0, 0.0, false, 0)
ON CONFLICT DO NOTHING;

INSERT INTO shipments (order_id, tracking_number, carrier, status, origin_region, destination_region, weight_kg, shipping_cost) VALUES
    (1, 'FDX-MS-001', 'fedex', 'delivered', 'us-east-1', 'us-east-1', 0.8, 9.99),
    (2, 'UPS-MS-001', 'ups', 'in_transit', 'us-west-2', 'eu-central-1', 1.5, 29.99),
    (3, 'DHL-MS-001', 'dhl', 'processing', 'eu-central-1', 'ap-northeast-1', 0.4, 19.99),
    (4, 'FDX-MS-002', 'fedex', 'shipped', 'us-east-1', 'us-west-2', 2.0, 14.99),
    (5, 'USPS-MS-001', 'usps', 'delivered', 'us-east-1', 'us-east-1', 0.3, 5.99),
    (6, 'DHL-MS-002', 'dhl', 'in_transit', 'eu-central-1', 'sa-east-1', 1.2, 39.99)
ON CONFLICT DO NOTHING;

INSERT INTO warehouses (name, region, address, capacity, current_stock, is_active) VALUES
    ('US East Fulfillment', 'us-east-1', '100 Cloud Way, Virginia', 50000, 32000, true),
    ('EU Central Hub', 'eu-central-1', '50 MuShop Str., Frankfurt', 30000, 18000, true),
    ('APAC Distribution', 'ap-southeast-1', '88 Container Rd, Singapore', 20000, 8500, true),
    ('US West Warehouse', 'us-west-2', '200 K8s Ave, Oregon', 25000, 15000, true)
ON CONFLICT DO NOTHING;

INSERT INTO campaigns (name, campaign_type, status, budget, spent, target_audience, start_date) VALUES
    ('Launch Sale', 'email', 'completed', 25000, 24500, 'All customers', '2024-01-01'),
    ('Summer Collection', 'social', 'active', 15000, 6000, 'Young professionals', '2024-06-01'),
    ('DevOps Swag Drop', 'ppc', 'active', 10000, 4200, 'DevOps engineers', '2024-04-01'),
    ('Partner Program', 'referral', 'active', 50000, 18000, 'Cloud partners', '2024-01-01')
ON CONFLICT DO NOTHING;

INSERT INTO leads (campaign_id, email, name, source, status, score) VALUES
    (1, 'lead1@techco.com', 'Alice Smith', 'web', 'converted', 92),
    (1, 'lead2@startup.io', 'Bob Jones', 'referral', 'qualified', 78),
    (2, 'lead3@bigcorp.com', 'Carol Lee', 'social', 'contacted', 65),
    (2, 'lead4@dev.tools', 'Dave Brown', 'paid', 'new', 40),
    (3, 'lead5@sre.team', 'Eve Wilson', 'web', 'qualified', 85),
    (4, 'lead6@cloud.partner', 'Frank Chen', 'referral', 'converted', 95)
ON CONFLICT DO NOTHING;

INSERT INTO page_views (page, visitor_ip, visitor_region, load_time_ms, session_id) VALUES
    ('/shop', '10.0.1.1', 'eu-central-1', 95, 'sess-001'),
    ('/catalogue', '10.0.1.1', 'eu-central-1', 110, 'sess-001'),
    ('/shop', '10.0.2.1', 'us-east-1', 180, 'sess-002'),
    ('/shop', '10.0.3.1', 'ap-northeast-1', 420, 'sess-003'),
    ('/orders', '10.0.3.1', 'ap-northeast-1', 380, 'sess-003'),
    ('/shop', '10.0.4.1', 'us-west-2', 200, 'sess-004'),
    ('/analytics', '10.0.5.1', 'ap-southeast-1', 510, 'sess-005'),
    ('/shop', '10.0.6.1', 'sa-east-1', 650, 'sess-006'),
    ('/catalogue', '10.0.7.1', 'af-south-1', 870, 'sess-007'),
    ('/shop', '10.0.1.2', 'eu-central-1', 88, 'sess-008')
ON CONFLICT DO NOTHING;
