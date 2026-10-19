# Sample E-commerce Tenant Database

Use this folder to create a small Supabase project that behaves like a real tenant business database.

Run these files in the Supabase SQL Editor in order:

1. `001_schema.sql`
2. `002_seed.sql`
3. Optional: `003_readonly_role_template.sql`

The data is intentionally small:

- 20 customers
- 8 categories
- 18 products
- 32 orders
- 43 order items
- 20 customer segment rows
- 6 campaign rows

Good test questions after connecting this database:

- Who are my top customers by lifetime value?
- Which products sold the most last month?
- Which categories generate the most revenue?
- Find high-value customers with high churn risk.
- Which campaigns have the best conversion rate?
- Suggest a retention campaign for customers likely to churn.
- Which products are low in stock but highly rated?
- What should I promote to Gold loyalty customers?

For BandhanAI, connect using a read-only URI, not the Supabase `postgres` superuser URI.
