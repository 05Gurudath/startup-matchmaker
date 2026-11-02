-- =====================================================================
-- Startup Matchmaker - MySQL schema
--
-- Reconstructed from the queries used in backend/ and matching_engine.py.
-- Usage:
--     mysql -u root -p < database/schema.sql
-- =====================================================================

CREATE DATABASE IF NOT EXISTS startup_matchmaker
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE startup_matchmaker;

-- ---------------------------------------------------------------------
-- users: login accounts (passwords are stored as Argon2 hashes)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    email          VARCHAR(150) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    role           VARCHAR(20)  NOT NULL,
    CONSTRAINT chk_users_role CHECK (role IN ('Admin', 'Startup', 'Investor'))
);

-- ---------------------------------------------------------------------
-- industries: lookup table shared by startups and investor preferences
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS industries (
    industry_id    INT AUTO_INCREMENT PRIMARY KEY,
    industry_name  VARCHAR(100) NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------
-- startups: each startup is owned by (at most) one Startup user
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS startups (
    startup_id        INT AUTO_INCREMENT PRIMARY KEY,
    user_id           INT NULL,
    name              VARCHAR(150) NOT NULL,
    description       TEXT NULL,
    industry_id       INT NOT NULL,
    stage             VARCHAR(50)  NOT NULL,
    location          VARCHAR(100) NULL,
    funding_required  DECIMAL(15, 2) NULL,
    founded_year      INT NULL,
    CONSTRAINT fk_startups_user
        FOREIGN KEY (user_id) REFERENCES users (user_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_startups_industry
        FOREIGN KEY (industry_id) REFERENCES industries (industry_id)
);

-- ---------------------------------------------------------------------
-- investors and their investment preferences (one row per industry)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS investors (
    investor_id      INT AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    organization     VARCHAR(150) NULL,
    investor_type    VARCHAR(50)  NULL,
    location         VARCHAR(100) NULL,
    min_investment   DECIMAL(15, 2) NULL,
    max_investment   DECIMAL(15, 2) NULL,
    website          VARCHAR(255) NULL
);

CREATE TABLE IF NOT EXISTS investor_preferences (
    preference_id       INT AUTO_INCREMENT PRIMARY KEY,
    investor_id         INT NOT NULL,
    industry_id         INT NOT NULL,
    preferred_stage     VARCHAR(50)  NULL,
    min_check_size      DECIMAL(15, 2) NULL,
    max_check_size      DECIMAL(15, 2) NULL,
    preferred_location  VARCHAR(100) NULL,
    CONSTRAINT fk_pref_investor
        FOREIGN KEY (investor_id) REFERENCES investors (investor_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_pref_industry
        FOREIGN KEY (industry_id) REFERENCES industries (industry_id)
);

-- ---------------------------------------------------------------------
-- pitch_decks: metadata for uploaded decks. The extracted text chunks
-- live in ChromaDB and link back via mysql_deck_id / mysql_startup_id.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pitch_decks (
    deck_id          INT AUTO_INCREMENT PRIMARY KEY,
    startup_id       INT NOT NULL,
    file_name        VARCHAR(255) NOT NULL,
    file_type        VARCHAR(20)  NOT NULL,
    upload_date      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version          VARCHAR(20)  NOT NULL,
    analysis_status  VARCHAR(30)  NOT NULL,
    INDEX idx_decks_startup_date (startup_id, upload_date),
    CONSTRAINT fk_decks_startup
        FOREIGN KEY (startup_id) REFERENCES startups (startup_id)
        ON DELETE CASCADE
);

-- ---------------------------------------------------------------------
-- match_results: scored startup <-> investor matches (0-100 per dimension)
-- A dimension score is NULL when the data needed to compute it is missing.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS match_results (
    match_id          INT AUTO_INCREMENT PRIMARY KEY,
    startup_id        INT NOT NULL,
    investor_id       INT NOT NULL,
    match_score       DECIMAL(5, 2) NOT NULL,
    industry_score    DECIMAL(5, 2) NULL,
    stage_score       DECIMAL(5, 2) NULL,
    investment_score  DECIMAL(5, 2) NULL,
    location_score    DECIMAL(5, 2) NULL,
    similarity_score  DECIMAL(5, 2) NULL,
    generated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_match_startup_score (startup_id, match_score),
    CONSTRAINT fk_match_startup
        FOREIGN KEY (startup_id) REFERENCES startups (startup_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_match_investor
        FOREIGN KEY (investor_id) REFERENCES investors (investor_id)
        ON DELETE CASCADE
);
