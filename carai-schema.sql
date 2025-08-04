-- Enable UUID extension (PostgreSQL only)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- USERS TABLE
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- VEHICLES TABLE
CREATE TABLE vehicles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  year TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- MODS LIBRARY TABLE (predefined mod types)
CREATE TABLE mods_library (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT UNIQUE NOT NULL,
  category TEXT,
  description TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- VEHICLE MODS TABLE (actual installed mods)
CREATE TABLE vehicle_mods (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  vehicle_id UUID REFERENCES vehicles(id) ON DELETE CASCADE,
  name TEXT NOT NULL, -- user-defined or overridden name
  description TEXT,
  installed_on DATE,
  mod_library_id UUID REFERENCES mods_library(id),
  created_at TIMESTAMP DEFAULT NOW()
);

-- MOD DOCUMENTS TABLE (photos, receipts, etc.)
CREATE TABLE mod_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mod_id UUID REFERENCES vehicle_mods(id) ON DELETE CASCADE,
  file_url TEXT NOT NULL,
  file_type TEXT,    -- e.g., image/jpeg, application/pdf
  label TEXT,        -- e.g., "Receipt", "Before Photo"
  uploaded_at TIMESTAMP DEFAULT NOW()
);

-- CONVERSATIONS TABLE
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  vehicle_id UUID REFERENCES vehicles(id) ON DELETE CASCADE,
  title TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- MESSAGES TABLE
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  sender TEXT CHECK (sender IN ('user', 'ai')) NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO mods_library (name, category, description) VALUES
  ('Cold Air Intake', 'Intake', 'Improves airflow to the engine'),
  ('Cat-Back Exhaust', 'Exhaust', 'Performance exhaust system from catalytic converter back'),
  ('Stage 1 Tune', 'ECU', 'Basic performance tune for stock components'),
  ('Coilover Suspension', 'Suspension', 'Adjustable ride height and damping control'),
  ('Short Throw Shifter', 'Drivetrain', 'Reduces shift travel for quicker gear changes');
