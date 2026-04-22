-- Enterprise CRM Portal - Database Initialization
-- Creates tables and seeds demo data

-- Users
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

-- Customers
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

-- Shops
CREATE TABLE IF NOT EXISTS shops (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(80) UNIQUE NOT NULL,
    storefront_url VARCHAR(500) NOT NULL,
    crm_base_url VARCHAR(500) NOT NULL,
    region VARCHAR(80) NOT NULL,
    currency VARCHAR(10) DEFAULT 'USD',
    status VARCHAR(50) DEFAULT 'active',
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Products
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER REFERENCES shops(id),
    name VARCHAR(200) NOT NULL,
    sku VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    price FLOAT NOT NULL,
    stock INTEGER DEFAULT 0,
    category VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    total FLOAT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    notes TEXT,
    shipping_address TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Order Items
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price FLOAT NOT NULL
);

-- Invoices
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    amount FLOAT NOT NULL,
    tax FLOAT DEFAULT 0.0,
    status VARCHAR(50) DEFAULT 'unpaid',
    due_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Support Tickets
CREATE TABLE IF NOT EXISTS support_tickets (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    subject VARCHAR(300) NOT NULL,
    description TEXT,
    priority VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(50) DEFAULT 'open',
    assigned_to VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(200),
    details TEXT,
    ip_address VARCHAR(50),
    user_agent VARCHAR(500),
    trace_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Reports
CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    report_type VARCHAR(50),
    query TEXT,
    parameters TEXT,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Campaigns
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
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Leads
CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER REFERENCES campaigns(id),
    customer_id INTEGER REFERENCES customers(id),
    email VARCHAR(200) NOT NULL,
    name VARCHAR(200),
    source VARCHAR(100),
    status VARCHAR(50) DEFAULT 'new',
    score INTEGER DEFAULT 0,
    notes TEXT,
    converted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Shipments
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
    actual_delivery TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Page Views (analytics)
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

-- Warehouses
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

-- ── Seed Data ────────────────────────────────────────────────────

-- Bootstrap users are created by the application at runtime using
-- BOOTSTRAP_ADMIN_PASSWORD or BOOTSTRAP_ADMIN_PASSWORD_FILE.

-- Customers
INSERT INTO customers (name, email, phone, company, industry, revenue) VALUES
    ('Acme Corporation', 'contact@acme.com', '+1-555-0101', 'Acme Corp', 'Manufacturing', 5200000),
    ('Globex Industries', 'info@globex.com', '+1-555-0102', 'Globex', 'Technology', 12800000),
    ('Initech Solutions', 'sales@initech.com', '+1-555-0103', 'Initech', 'Consulting', 3400000),
    ('Umbrella Corp', 'biz@umbrella.com', '+1-555-0104', 'Umbrella', 'Pharmaceuticals', 45000000),
    ('Stark Industries', 'tony@stark.com', '+1-555-0105', 'Stark Ind', 'Defense', 89000000),
    ('Wayne Enterprises', 'bruce@wayne.com', '+1-555-0106', 'Wayne Ent', 'Conglomerate', 120000000),
    ('Cyberdyne Systems', 'info@cyberdyne.com', '+1-555-0107', 'Cyberdyne', 'AI/Robotics', 8900000),
    ('Oscorp Industries', 'norman@oscorp.com', '+1-555-0108', 'Oscorp', 'Biotech', 22000000),
    ('LexCorp', 'lex@lexcorp.com', '+1-555-0109', 'LexCorp', 'Energy', 67000000),
    ('Weyland-Yutani', 'corp@weyland.com', '+1-555-0110', 'Weyland', 'Space/Mining', 150000000)
ON CONFLICT DO NOTHING;

-- Shops
INSERT INTO shops (name, slug, storefront_url, crm_base_url, region, currency, status, notes) VALUES
    ('Primary Storefront', 'primary-store', 'https://shop.example.cloud', 'https://crm.example.cloud', 'eu-central', 'USD', 'active', 'Primary public storefront managed from CRM.'),
    ('Lab Storefront', 'lab-store', 'https://shop-lab.example.cloud', 'https://crm.example.cloud', 'us-east', 'USD', 'maintenance', 'Sandbox storefront for catalog rehearsals.')
ON CONFLICT DO NOTHING;

-- Products
INSERT INTO products (shop_id, name, sku, description, price, stock, category) VALUES
    (1, 'Enterprise License', 'ENT-001', 'Full enterprise software license', 99999.00, 100, 'License'),
    (1, 'Professional License', 'PRO-001', 'Professional tier license', 29999.00, 500, 'License'),
    (1, 'Basic License', 'BAS-001', 'Basic tier license', 9999.00, 1000, 'License'),
    (1, 'Premium Support', 'SUP-001', '24/7 premium support package', 14999.00, 200, 'Support'),
    (1, 'Standard Support', 'SUP-002', 'Business hours support', 4999.00, 500, 'Support'),
    (1, 'Cloud Hosting', 'CLD-001', 'Managed cloud hosting per year', 19999.00, 300, 'Infrastructure'),
    (1, 'Data Migration', 'SRV-001', 'Data migration service', 24999.00, 50, 'Services'),
    (1, 'Training Package', 'TRN-001', 'On-site training (5 days)', 7999.00, 100, 'Training'),
    (1, 'API Access', 'API-001', 'API integration tier', 5999.00, 1000, 'Integration'),
    (1, 'Security Audit', 'SEC-001', 'Comprehensive security audit', 34999.00, 20, 'Security')
ON CONFLICT DO NOTHING;

-- Orders
INSERT INTO orders (customer_id, total, status, shipping_address) VALUES
    (1, 129998.00, 'completed', '123 Industrial Way, Springfield'),
    (2, 44998.00, 'processing', '456 Tech Park, Silicon Valley'),
    (3, 39998.00, 'pending', '789 Consulting Blvd, New York'),
    (4, 99999.00, 'completed', '321 Pharma Drive, Raccoon City'),
    (5, 154998.00, 'shipped', '10880 Malibu Point, CA'),
    (1, 14999.00, 'completed', '123 Industrial Way, Springfield'),
    (6, 269997.00, 'processing', '1007 Mountain Drive, Gotham'),
    (7, 29999.00, 'pending', '18144 El Camino Real, Sunnyvale')
ON CONFLICT DO NOTHING;

-- Order Items
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1, 1, 1, 99999.00), (1, 4, 2, 14999.00),
    (2, 2, 1, 29999.00), (2, 4, 1, 14999.00),
    (3, 2, 1, 29999.00), (3, 8, 1, 7999.00),
    (4, 1, 1, 99999.00),
    (5, 1, 1, 99999.00), (5, 6, 1, 19999.00), (5, 10, 1, 34999.00),
    (6, 4, 1, 14999.00),
    (7, 1, 2, 99999.00), (7, 6, 1, 19999.00), (7, 10, 2, 34999.00),
    (8, 2, 1, 29999.00)
ON CONFLICT DO NOTHING;

-- Invoices
INSERT INTO invoices (order_id, invoice_number, amount, tax, status, due_date) VALUES
    (1, 'INV-2024-001', 129998.00, 10399.84, 'paid', '2024-02-15'),
    (2, 'INV-2024-002', 44998.00, 3599.84, 'paid', '2024-03-01'),
    (3, 'INV-2024-003', 39998.00, 3199.84, 'overdue', '2024-01-15'),
    (4, 'INV-2024-004', 99999.00, 7999.92, 'paid', '2024-04-01'),
    (5, 'INV-2024-005', 154998.00, 12399.84, 'unpaid', '2024-05-01'),
    (6, 'INV-2024-006', 14999.00, 1199.92, 'paid', '2024-03-15'),
    (7, 'INV-2024-007', 269997.00, 21599.76, 'unpaid', '2024-06-01'),
    (8, 'INV-2024-008', 29999.00, 2399.92, 'pending', '2024-06-15')
ON CONFLICT DO NOTHING;

-- Support Tickets
INSERT INTO support_tickets (customer_id, subject, description, priority, status, assigned_to) VALUES
    (1, 'License activation failed', 'Cannot activate enterprise license on new server', 'high', 'open', 'user1'),
    (2, 'API rate limiting', 'Getting 429 errors when calling batch API', 'medium', 'in_progress', 'admin'),
    (3, 'Slow dashboard loading', 'Dashboard takes 30+ seconds to load', 'high', 'open', 'user1'),
    (4, 'Data export issue', 'CSV export corrupts unicode characters', 'low', 'resolved', 'manager'),
    (5, 'SSO integration', 'Need help configuring SAML SSO', 'medium', 'open', 'admin'),
    (1, 'Billing discrepancy', 'Invoice amount does not match order total', 'high', 'open', 'manager'),
    (6, 'Custom report builder', 'Report builder crashes on large datasets', 'critical', 'in_progress', 'admin'),
    (7, 'Migration stuck at 80%', 'Data migration process hung', 'critical', 'open', 'user1')
ON CONFLICT DO NOTHING;

-- Campaigns
INSERT INTO campaigns (name, campaign_type, status, budget, spent, target_audience, start_date, end_date, created_by) VALUES
    ('Q1 Product Launch', 'email', 'completed', 50000, 48500, 'Enterprise customers', '2024-01-01', '2024-03-31', 1),
    ('Summer Sale 2024', 'social', 'active', 30000, 12000, 'SMB segment', '2024-06-01', '2024-08-31', 1),
    ('Security Webinar Series', 'email', 'active', 15000, 8200, 'CISOs and security teams', '2024-04-01', '2024-12-31', 3),
    ('Cloud Migration Guide', 'ppc', 'paused', 25000, 18900, 'IT decision makers', '2024-03-01', '2024-06-30', 1),
    ('Partner Referral Program', 'referral', 'active', 100000, 35000, 'Channel partners', '2024-01-01', '2024-12-31', 3),
    ('APAC Market Entry', 'social', 'draft', 75000, 0, 'APAC enterprise segment', '2024-09-01', '2025-03-31', 1)
ON CONFLICT DO NOTHING;

-- Leads
INSERT INTO leads (campaign_id, customer_id, email, name, source, status, score, notes) VALUES
    (1, 1, 'new-lead@acme.com', 'John Smith', 'web', 'qualified', 85, 'Interested in enterprise tier'),
    (1, NULL, 'prospect@techcorp.com', 'Jane Doe', 'referral', 'contacted', 60, 'Referred by Globex'),
    (2, 2, 'sales@globex.com', 'Bob Wilson', 'social', 'converted', 95, 'Upgraded to professional'),
    (2, NULL, 'info@newco.com', 'Alice Brown', 'paid', 'new', 30, 'Downloaded whitepaper'),
    (3, 4, 'security@umbrella.com', 'Eve Chen', 'web', 'qualified', 78, 'Attended 2 webinars'),
    (3, NULL, 'ciso@bigbank.com', 'Frank Lee', 'referral', 'contacted', 65, 'Follow-up scheduled'),
    (4, NULL, 'it@startup.io', 'Grace Kim', 'paid', 'lost', 40, 'Went with competitor'),
    (5, 5, 'partner@stark.com', 'Tony Stark', 'referral', 'converted', 100, 'Became reseller partner'),
    (5, 6, 'partner@wayne.com', 'Bruce Wayne', 'referral', 'qualified', 88, 'Evaluating partnership'),
    (2, NULL, 'buyer@smallbiz.com', 'Dave Miller', 'social', 'new', 25, 'Clicked ad on LinkedIn')
ON CONFLICT DO NOTHING;

-- Shipments
INSERT INTO shipments (order_id, tracking_number, carrier, status, origin_region, destination_region, weight_kg, shipping_cost, estimated_delivery) VALUES
    (1, 'FDX-2024-001', 'fedex', 'delivered', 'us-east-1', 'us-east-1', 2.5, 29.99, '2024-01-20'),
    (2, 'UPS-2024-001', 'ups', 'in_transit', 'us-west-2', 'us-west-2', 1.8, 24.99, '2024-03-15'),
    (3, 'DHL-2024-001', 'dhl', 'shipped', 'eu-central-1', 'us-east-1', 3.2, 89.99, '2024-02-28'),
    (4, 'FDX-2024-002', 'fedex', 'delivered', 'us-east-1', 'eu-central-1', 0.5, 45.99, '2024-04-10'),
    (5, 'UPS-2024-002', 'ups', 'in_transit', 'us-west-2', 'ap-northeast-1', 4.1, 149.99, '2024-05-20'),
    (6, 'FDX-2024-003', 'fedex', 'delivered', 'us-east-1', 'us-east-1', 0.3, 15.99, '2024-03-20'),
    (7, 'DHL-2024-002', 'dhl', 'processing', 'eu-central-1', 'us-east-1', 5.5, 129.99, '2024-06-15'),
    (8, 'USPS-2024-001', 'usps', 'shipped', 'us-east-1', 'ap-southeast-1', 1.2, 79.99, '2024-07-01')
ON CONFLICT DO NOTHING;

-- Warehouses
INSERT INTO warehouses (name, region, address, capacity, current_stock, is_active) VALUES
    ('US East Hub', 'us-east-1', '100 Fulfillment Way, Virginia', 50000, 32000, true),
    ('US West Hub', 'us-west-2', '200 Distribution Ave, Oregon', 35000, 18500, true),
    ('EU Central Hub', 'eu-central-1', '50 Logistics Str., Frankfurt', 40000, 27000, true),
    ('APAC Hub', 'ap-southeast-1', '88 Warehouse Rd, Singapore', 25000, 12000, true),
    ('APAC Northeast', 'ap-northeast-1', '1-2-3 Logistics, Tokyo', 20000, 8500, true),
    ('South America', 'sa-east-1', 'Rua Logistica 100, São Paulo', 15000, 5200, true),
    ('Middle East', 'me-south-1', 'Industrial City, Bahrain', 10000, 3200, false)
ON CONFLICT DO NOTHING;

-- Page Views (seed some demo data for analytics)
INSERT INTO page_views (page, visitor_ip, visitor_region, load_time_ms, session_id) VALUES
    ('/dashboard', '10.0.1.1', 'eu-central-1', 120, 'sess-001'),
    ('/customers', '10.0.1.1', 'eu-central-1', 95, 'sess-001'),
    ('/orders', '10.0.2.1', 'us-east-1', 180, 'sess-002'),
    ('/dashboard', '10.0.3.1', 'ap-northeast-1', 450, 'sess-003'),
    ('/products', '10.0.3.1', 'ap-northeast-1', 380, 'sess-003'),
    ('/dashboard', '10.0.4.1', 'us-west-2', 210, 'sess-004'),
    ('/analytics', '10.0.5.1', 'ap-southeast-1', 520, 'sess-005'),
    ('/dashboard', '10.0.6.1', 'sa-east-1', 680, 'sess-006'),
    ('/customers', '10.0.7.1', 'af-south-1', 890, 'sess-007'),
    ('/tickets', '10.0.1.2', 'eu-central-1', 110, 'sess-008')
ON CONFLICT DO NOTHING;
