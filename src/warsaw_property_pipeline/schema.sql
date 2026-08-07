CREATE TABLE IF NOT EXISTS developers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS investments (
    id BIGSERIAL PRIMARY KEY,
    developer_id BIGINT NOT NULL REFERENCES developers(id),
    name TEXT NOT NULL,
    city TEXT NOT NULL DEFAULT 'Warszawa',
    district TEXT,
    street TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (developer_id, name)
);

CREATE TABLE IF NOT EXISTS apartments (
    id BIGSERIAL PRIMARY KEY,
    investment_id BIGINT NOT NULL REFERENCES investments(id),
    source_apartment_id TEXT NOT NULL,
    property_type TEXT NOT NULL,
    area_m2 NUMERIC(10, 2) NOT NULL CHECK (area_m2 > 0),
    rooms INTEGER CHECK (rooms IS NULL OR rooms >= 0),
    floor TEXT,
    available BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (investment_id, source_apartment_id)
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id BIGSERIAL PRIMARY KEY,
    apartment_id BIGINT NOT NULL REFERENCES apartments(id),
    observed_on DATE NOT NULL,
    price_valid_from DATE NOT NULL,
    area_m2 NUMERIC(10, 2) NOT NULL CHECK (area_m2 > 0),
    price_pln NUMERIC(14, 2) NOT NULL CHECK (price_pln > 0),
    price_per_m2 NUMERIC(12, 2) NOT NULL CHECK (price_per_m2 > 0),
    currency CHAR(3) NOT NULL DEFAULT 'PLN' CHECK (currency = 'PLN'),
    source_name TEXT NOT NULL,
    source_resource_id TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (apartment_id, observed_on)
);

CREATE INDEX IF NOT EXISTS idx_price_snapshots_observed_on
    ON price_snapshots (observed_on DESC);
CREATE INDEX IF NOT EXISTS idx_investments_district
    ON investments (district);

CREATE OR REPLACE VIEW latest_apartment_prices AS
SELECT DISTINCT ON (a.id)
    a.id AS apartment_id,
    d.name AS developer,
    i.name AS investment,
    i.district,
    a.source_apartment_id,
    a.rooms,
    ps.area_m2,
    ps.price_pln,
    ps.price_per_m2,
    ps.observed_on
FROM apartments a
JOIN investments i ON i.id = a.investment_id
JOIN developers d ON d.id = i.developer_id
JOIN price_snapshots ps ON ps.apartment_id = a.id
ORDER BY a.id, ps.observed_on DESC;

CREATE OR REPLACE VIEW apartment_price_changes AS
WITH ordered AS (
    SELECT
        ps.*,
        lag(ps.price_pln) OVER (
            PARTITION BY ps.apartment_id ORDER BY ps.observed_on
        ) AS previous_price_pln
    FROM price_snapshots ps
)
SELECT
    a.id AS apartment_id,
    d.name AS developer,
    i.name AS investment,
    i.district,
    a.source_apartment_id,
    ordered.observed_on,
    ordered.previous_price_pln,
    ordered.price_pln AS current_price_pln,
    ordered.price_pln - ordered.previous_price_pln AS price_change_pln,
    round(
        100 * (ordered.price_pln - ordered.previous_price_pln)
        / NULLIF(ordered.previous_price_pln, 0),
        2
    ) AS price_change_percent
FROM ordered
JOIN apartments a ON a.id = ordered.apartment_id
JOIN investments i ON i.id = a.investment_id
JOIN developers d ON d.id = i.developer_id
WHERE ordered.previous_price_pln IS NOT NULL;

CREATE OR REPLACE VIEW district_statistics AS
SELECT
    district,
    count(*) AS apartment_count,
    round(avg(price_per_m2), 2) AS avg_price_per_m2,
    min(price_per_m2) AS min_price_per_m2,
    max(price_per_m2) AS max_price_per_m2
FROM latest_apartment_prices
GROUP BY district;

