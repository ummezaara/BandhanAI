-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.campaigns (
  campaign_id text NOT NULL,
  campaign_name text,
  type text,
  created_date text,
  target_segment text,
  sent bigint,
  opened bigint,
  clicked bigint,
  converted bigint,
  CONSTRAINT campaigns_pkey PRIMARY KEY (campaign_id)
);
CREATE TABLE public.customers (
  customer_id text NOT NULL,
  first_name text,
  last_name text,
  email text,
  phone bigint,
  gender text,
  age bigint,
  city text,
  state text,
  country text,
  signup_date text,
  preferred_category text,
  loyalty_tier text,
  total_orders bigint,
  total_spent bigint,
  avg_order_value numeric,
  last_purchase_date text,
  status text,
  CONSTRAINT customers_pkey PRIMARY KEY (customer_id)
);
CREATE TABLE public.orders (
  order_id text NOT NULL,
  customer_id text,
  order_date text,
  product_id text,
  quantity bigint,
  unit_price bigint,
  total_amount bigint,
  payment_method text,
  order_status text,
  CONSTRAINT orders_pkey PRIMARY KEY (order_id)
);
CREATE TABLE public.products (
  product_id text NOT NULL,
  product_name text,
  category text,
  brand text,
  price bigint,
  cost_price double precision,
  stock bigint,
  rating double precision,
  CONSTRAINT products_pkey PRIMARY KEY (product_id)
);
CREATE TABLE public.segments (
  customer_id text NOT NULL,
  segment text,
  churn_score double precision,
  lifetime_value bigint,
  predicted_next_purchase text,
  CONSTRAINT segments_pkey PRIMARY KEY (customer_id)
);