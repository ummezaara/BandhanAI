-- ============================================================================
-- Sample E-commerce Tenant Schema for BandhanAI
-- ============================================================================
-- Run in a fresh Supabase project SQL Editor.

DROP TABLE IF EXISTS public.campaign_events;
DROP TABLE IF EXISTS public.campaigns;
DROP TABLE IF EXISTS public.customer_segments;
DROP TABLE IF EXISTS public.order_items;
DROP TABLE IF EXISTS public.orders;
DROP TABLE IF EXISTS public.products;
DROP TABLE IF EXISTS public.categories;
DROP TABLE IF EXISTS public.customers;

CREATE TABLE public.customers (
    customer_id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    gender TEXT,
    age INTEGER,
    city TEXT,
    state TEXT,
    country TEXT DEFAULT 'India',
    signup_date DATE NOT NULL,
    preferred_category TEXT,
    loyalty_tier TEXT CHECK (loyalty_tier IN ('Bronze', 'Silver', 'Gold', 'Platinum')),
    status TEXT CHECK (status IN ('active', 'inactive', 'at_risk', 'lost')),
    total_orders INTEGER DEFAULT 0,
    total_spent NUMERIC(12, 2) DEFAULT 0,
    avg_order_value NUMERIC(12, 2) DEFAULT 0,
    last_purchase_date DATE
);

CREATE TABLE public.categories (
    category_id TEXT PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE,
    parent_category TEXT
);

CREATE TABLE public.products (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    category_id TEXT REFERENCES public.categories(category_id),
    category TEXT NOT NULL,
    brand TEXT,
    price NUMERIC(12, 2) NOT NULL,
    cost_price NUMERIC(12, 2) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    rating NUMERIC(3, 2),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE public.orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES public.customers(customer_id),
    order_date DATE NOT NULL,
    payment_method TEXT CHECK (payment_method IN ('UPI', 'Credit Card', 'Debit Card', 'COD', 'Net Banking')),
    order_status TEXT CHECK (order_status IN ('delivered', 'shipped', 'processing', 'cancelled', 'returned')),
    total_amount NUMERIC(12, 2) NOT NULL
);

CREATE TABLE public.order_items (
    order_item_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES public.orders(order_id) ON DELETE CASCADE,
    product_id TEXT NOT NULL REFERENCES public.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL,
    line_total NUMERIC(12, 2) NOT NULL
);

CREATE TABLE public.customer_segments (
    customer_id TEXT PRIMARY KEY REFERENCES public.customers(customer_id) ON DELETE CASCADE,
    segment TEXT NOT NULL,
    churn_score NUMERIC(4, 3) NOT NULL CHECK (churn_score >= 0 AND churn_score <= 1),
    lifetime_value NUMERIC(12, 2) NOT NULL,
    predicted_next_purchase DATE,
    recommended_action TEXT
);

CREATE TABLE public.campaigns (
    campaign_id TEXT PRIMARY KEY,
    campaign_name TEXT NOT NULL,
    campaign_type TEXT NOT NULL,
    created_date DATE NOT NULL,
    target_segment TEXT,
    target_category TEXT,
    sent INTEGER DEFAULT 0,
    opened INTEGER DEFAULT 0,
    clicked INTEGER DEFAULT 0,
    converted INTEGER DEFAULT 0,
    revenue_generated NUMERIC(12, 2) DEFAULT 0
);

CREATE TABLE public.campaign_events (
    event_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES public.campaigns(campaign_id) ON DELETE CASCADE,
    customer_id TEXT NOT NULL REFERENCES public.customers(customer_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('sent', 'opened', 'clicked', 'converted')),
    event_date DATE NOT NULL
);

CREATE INDEX idx_orders_customer_id ON public.orders(customer_id);
CREATE INDEX idx_orders_order_date ON public.orders(order_date);
CREATE INDEX idx_order_items_order_id ON public.order_items(order_id);
CREATE INDEX idx_order_items_product_id ON public.order_items(product_id);
CREATE INDEX idx_products_category ON public.products(category);
CREATE INDEX idx_customer_segments_segment ON public.customer_segments(segment);
CREATE INDEX idx_customer_segments_churn_score ON public.customer_segments(churn_score);
