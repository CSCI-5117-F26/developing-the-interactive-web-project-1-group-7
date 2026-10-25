-- HARMless Mixtape Database Schema

-- 1. USERS
CREATE TABLE users (
    auth0_id TEXT PRIMARY KEY,
    username VARCHAR(50) UNIQUE,
    name TEXT,
    email TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. MIXTAPES
CREATE TABLE mixtapes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    creator_id TEXT NOT NULL
        REFERENCES users(auth0_id),

    title VARCHAR(150) NOT NULL,
    description TEXT,
    cover_image_url TEXT,

    remixed_from_id BIGINT
        REFERENCES mixtapes(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. SPOTIFY TRACKS
CREATE TABLE tracks (
    spotify_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    duration_ms INTEGER,
    album_image_url TEXT
);

-- 4. MIXTAPE TRACKS
CREATE TABLE mixtape_tracks (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    mixtape_id BIGINT NOT NULL
        REFERENCES mixtapes(id) ON DELETE CASCADE,

    spotify_id TEXT NOT NULL
        REFERENCES tracks(spotify_id),

    position INTEGER NOT NULL CHECK (position > 0),
    annotation TEXT,
    added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (mixtape_id, position)
);

-- 5. MIXTAPE TAGS
CREATE TABLE mixtape_tags (
    mixtape_id BIGINT NOT NULL
        REFERENCES mixtapes(id) ON DELETE CASCADE,

    tag VARCHAR(50) NOT NULL,

    PRIMARY KEY (mixtape_id, tag)
);

-- 6. SAVED MIXTAPES
CREATE TABLE saved_mixtapes (
    user_id TEXT NOT NULL
        REFERENCES users(auth0_id),

    mixtape_id BIGINT NOT NULL
        REFERENCES mixtapes(id) ON DELETE CASCADE,

    saved_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id, mixtape_id)
);

-- 7. MIXTAPE LIKES
CREATE TABLE mixtape_likes (
    user_id TEXT NOT NULL
        REFERENCES users(auth0_id),

    mixtape_id BIGINT NOT NULL
        REFERENCES mixtapes(id) ON DELETE CASCADE,

    liked_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id, mixtape_id)
);

-- 8. IMAGES
CREATE TABLE images (
    image_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL
        REFERENCES users(auth0_id),
    mixtape_id BIGINT NOT NULL
        REFERENCES mixtapes(id) on DELETE CASCADE,
    stream BYTEA
);

-- Might be useful by making certain reads faster
-- INDEXES
CREATE INDEX idx_mixtapes_creator
    ON mixtapes(creator_id);

CREATE INDEX idx_mixtapes_remix
    ON mixtapes(remixed_from_id);

CREATE INDEX idx_mixtape_tracks_mixtape
    ON mixtape_tracks(mixtape_id);

CREATE INDEX idx_mixtape_tags_tag
    ON mixtape_tags(tag);

CREATE INDEX idx_saved_mixtapes_mixtape
    ON saved_mixtapes(mixtape_id);

CREATE INDEX idx_mixtape_likes_mixtape
    ON mixtape_likes(mixtape_id);
