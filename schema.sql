CREATE TABLE IF NOT EXISTS users (
    auth0_id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT
);

CREATE TABLE IF NOT EXISTS mixtapes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    creator_id TEXT NOT NULL REFERENCES users(auth0_id),
    title VARCHAR(150) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS saved_mixtapes (
    user_id TEXT NOT NULL REFERENCES users(auth0_id),
    mixtape_id BIGINT NOT NULL REFERENCES mixtapes(id) ON DELETE CASCADE,
    saved_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, mixtape_id)
);