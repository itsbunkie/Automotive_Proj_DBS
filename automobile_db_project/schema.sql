-- ============================================================
-- AUTOMOBILE COMPANY DATABASE — RELATIONAL SCHEMA (MySQL)
-- CSE 241/341 Project
--
-- This schema implements the entities named in the handout:
--   brands, models, vehicles, options, dealers, customers,
--   suppliers, parts, plants, sales, inventory
--
-- It maps directly onto the accompanying ER diagram (see
-- Automobile_Database notes): every strong entity below became a
-- table, every 1:M relationship became a foreign key on the
-- "many" side, and every M:N relationship (plant<->model,
-- dealer<->brand, model<->part) became its own junction table.
-- Comments on each table call out WHY a design choice was made
-- where the handout's spec was ambiguous, per its own warning
-- that "the manager... is not computer literate so the
-- specifications should not be viewed as necessarily... complete."
--
-- Run this with:  mysql -u <user> -p automobile_db < schema.sql
-- (create the database first: CREATE DATABASE automobile_db;)
-- db.py's init_db() runs this same file programmatically, so the
-- CLI and the Python path always build an identical schema.
-- ============================================================

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS locator_inquiries, vehicle_parts, model_parts,
    plant_models, dealer_brands, sales, vehicles, parts, models,
    platforms, customers, dealers, suppliers, plants, brands;

SET FOREIGN_KEY_CHECKS = 1;

-- ------------------------------------------------------------
-- BRANDS
-- A company (this whole DB) owns several brands, e.g. GM ->
-- Chevrolet, Buick, Cadillac, GMC, Saturn, Hummer, Saab...
-- ------------------------------------------------------------
CREATE TABLE brands (
    brand_id    INT AUTO_INCREMENT PRIMARY KEY,
    brand_name  VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- PLATFORMS  (resolves the ISA / badge-engineering relationship)
-- The handout explicitly calls out badge engineering: the VW
-- Routan is really a Chrysler minivan, and the Buick LaCrosse is
-- sold in Canada as the Buick Allure. In both cases, two distinct
-- (brand, model) rows are, underneath, the same vehicle — same
-- plant(s), same parts, same underlying engineering platform.
--
-- A superclass/subclass (ISA) relationship doesn't have a native
-- SQL construct, so the standard relational mapping is: promote
-- the shared concept to its own table (platforms) and give each
-- subclass row (models) a foreign key back up to it. Two models
-- sharing a platform_id ARE the badge-engineered pair — see the
-- ER diagram for the conceptual ISA arrow this table implements.
-- ------------------------------------------------------------
CREATE TABLE platforms (
    platform_id     INT AUTO_INCREMENT PRIMARY KEY,
    platform_name   VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- MODELS
-- Each brand offers several models, each of which may come in a
-- particular body style (4-door, wagon, coupe, convertible...).
--
-- DESIGN DECISION: body_style lives directly on the model row
-- rather than as its own weak entity. A separate model_variants
-- table would only be justified if each body-style variant needed
-- its own independent attributes (its own price, its own parts
-- list); the handout doesn't call for that granularity, and the
-- flatter design saves a join on every downstream query.
--
-- platform_id is NULLable BY DESIGN: most models stand alone with
-- no badge-engineered sibling, so partial participation in the
-- platform relationship is the expected, correct case, not a data
-- gap that needs to be filled in.
-- ------------------------------------------------------------
CREATE TABLE models (
    model_id    INT AUTO_INCREMENT PRIMARY KEY,
    brand_id    INT NOT NULL,
    model_name  VARCHAR(100) NOT NULL,
    body_style  VARCHAR(50),                 -- e.g. '4-door', 'wagon', 'coupe'
    platform_id INT,                         -- NULL = no badge-engineered sibling
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id),
    FOREIGN KEY (platform_id) REFERENCES platforms(platform_id),
    UNIQUE (brand_id, model_name, body_style)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- PLANTS
-- Some plants do final assembly; others just supply parts. We
-- track which models a plant assembles via plant_models below.
-- Because badge-engineered models (see platforms, above) share a
-- platform, they naturally end up pointing at the same assembly
-- plant too — that's the payoff of the platform table: it lets
-- shared manufacturing facts be represented once per platform
-- instead of duplicated per badge-model.
-- ------------------------------------------------------------
CREATE TABLE plants (
    plant_id    INT AUTO_INCREMENT PRIMARY KEY,
    plant_name  VARCHAR(150) NOT NULL,
    address     VARCHAR(255),
    plant_type  ENUM('assembly', 'parts', 'both') NOT NULL
) ENGINE=InnoDB;

CREATE TABLE plant_models (
    -- Which plant(s) assemble which model(s). Many-to-many:
    -- badge-engineered siblings on the same platform typically
    -- share a plant; a plant might assemble several models.
    plant_id    INT NOT NULL,
    model_id    INT NOT NULL,
    PRIMARY KEY (plant_id, model_id),
    FOREIGN KEY (plant_id) REFERENCES plants(plant_id),
    FOREIGN KEY (model_id) REFERENCES models(model_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- SUPPLIERS & PARTS
-- Suppliers supply certain parts for certain models. This pair of
-- tables (plus vehicle_parts, further down) is what makes the
-- "defective Getrag transmission" traceability query answerable.
--
-- DESIGN DECISION: supplying_plant_id is a single column on parts
-- rather than a separate supplier_plants junction table. A real
-- supplier certainly operates more than one plant, but the
-- handout's own defect scenario only ever needs to isolate ONE
-- plant per part ("suppose the defective transmissions all come
-- from only one of Getrag's plants") — a single FK captures that
-- without adding a table this project doesn't otherwise query.
-- ------------------------------------------------------------
CREATE TABLE suppliers (
    supplier_id     INT AUTO_INCREMENT PRIMARY KEY,
    supplier_name   VARCHAR(150) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE parts (
    part_id             INT AUTO_INCREMENT PRIMARY KEY,
    part_name           VARCHAR(100) NOT NULL,     -- e.g. 'Transmission', 'Engine Block'
    supplier_id         INT NOT NULL,
    supplying_plant_id  INT,                        -- which ONE plant supplied this batch
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    FOREIGN KEY (supplying_plant_id) REFERENCES plants(plant_id)
) ENGINE=InnoDB;

-- Which parts a given model is compatible with (many-to-many).
CREATE TABLE model_parts (
    model_id    INT NOT NULL,
    part_id     INT NOT NULL,
    PRIMARY KEY (model_id, part_id),
    FOREIGN KEY (model_id) REFERENCES models(model_id),
    FOREIGN KEY (part_id) REFERENCES parts(part_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- DEALERS
-- A dealer may not sell all of the company's brands, so we need a
-- junction table for "which brands does this dealer carry."
-- Defined before vehicles, since vehicles.current_dealer_id
-- references dealers(dealer_id).
-- ------------------------------------------------------------
CREATE TABLE dealers (
    dealer_id   INT AUTO_INCREMENT PRIMARY KEY,
    dealer_name VARCHAR(150) NOT NULL,
    address     VARCHAR(255),
    phone       VARCHAR(30)
) ENGINE=InnoDB;

CREATE TABLE dealer_brands (
    dealer_id   INT NOT NULL,
    brand_id    INT NOT NULL,
    PRIMARY KEY (dealer_id, brand_id),
    FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id),
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- VEHICLES
-- Each vehicle has a VIN (made up, per the handout — real VIN
-- checksums aren't required). We track which specific part (with
-- an install date) went into each specific VIN via vehicle_parts
-- below — that's the difference between "this MODEL can use a
-- Getrag transmission" (model_parts) and "this exact CAR got one,
-- installed on this exact date" (vehicle_parts), and only the
-- latter answers the recall-style query the handout asks for.
--
-- DESIGN DECISION: asking_price is a separate column from the
-- eventual sale_price recorded in sales. A vehicle sitting in
-- inventory has a listed price before any customer has agreed to
-- pay a (possibly negotiated) final price at sale time; keeping
-- these separate lets /search show honest pre-sale pricing
-- without faking a "sale" that hasn't happened yet.
-- ------------------------------------------------------------
CREATE TABLE vehicles (
    vin                     VARCHAR(17) PRIMARY KEY,   -- made up, per the handout
    model_id                INT NOT NULL,
    color                   VARCHAR(50),
    engine                  VARCHAR(50),
    transmission            VARCHAR(50),
    asking_price            DECIMAL(12,2),              -- pre-sale listed price
    manufacture_date        DATE,
    manufacturing_plant_id  INT,                         -- where THIS car was assembled
    -- Inventory tracking: which dealer currently holds it.
    current_dealer_id       INT,
    arrived_at_dealer_date  DATE,                        -- when THIS car reached that dealer's lot
    FOREIGN KEY (model_id) REFERENCES models(model_id),
    FOREIGN KEY (manufacturing_plant_id) REFERENCES plants(plant_id),
    FOREIGN KEY (current_dealer_id) REFERENCES dealers(dealer_id)
) ENGINE=InnoDB;

-- Which specific part (with its install date) went into a specific VIN.
CREATE TABLE vehicle_parts (
    vin             VARCHAR(17) NOT NULL,
    part_id         INT NOT NULL,
    install_date    DATE,
    PRIMARY KEY (vin, part_id),
    FOREIGN KEY (vin) REFERENCES vehicles(vin),
    FOREIGN KEY (part_id) REFERENCES parts(part_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- CUSTOMERS
-- Individual buyers only for this project (the handout says to
-- skip corporate fleet buyers like Hertz/Avis).
-- ------------------------------------------------------------
CREATE TABLE customers (
    customer_id     INT AUTO_INCREMENT PRIMARY KEY,
    full_name       VARCHAR(150) NOT NULL,
    address         VARCHAR(255),
    phone           VARCHAR(30),
    gender          ENUM('M', 'F', 'Other', 'Prefer not to say'),
    annual_income   DECIMAL(12,2)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- SALES
-- The core fact table. One row = one vehicle sold, at one dealer,
-- to one customer, on one date, for one price. Powers nearly
-- every required query (sales trends by brand/year/month/week/
-- gender/income, top brands by $ and units, best month for
-- convertibles, dealer inventory hold times).
-- ------------------------------------------------------------
CREATE TABLE sales (
    sale_id     INT AUTO_INCREMENT PRIMARY KEY,
    vin         VARCHAR(17) NOT NULL UNIQUE,   -- UNIQUE: each vehicle sold once
    dealer_id   INT NOT NULL,
    customer_id INT NOT NULL,
    sale_date   DATE NOT NULL,
    sale_price  DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (vin) REFERENCES vehicles(vin),
    FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- LOCATOR INQUIRIES
-- The handout's spec for the vehicle locator service notes that
-- "marketing may want to review these inquiries to do future
-- product planning." That sentence is itself a requirement: every
-- search a dealer runs through /locator gets logged here (see
-- app.py) so marketing has something concrete to review, distinct
-- from the six required OLAP queries against actual sales.
-- ------------------------------------------------------------
CREATE TABLE locator_inquiries (
    inquiry_id  INT AUTO_INCREMENT PRIMARY KEY,
    brand       VARCHAR(100),
    model       VARCHAR(100),
    color       VARCHAR(50),
    body_style  VARCHAR(50),
    searched_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- INDICES
-- These columns get filtered/grouped on constantly by the
-- required queries, so they're indexed rather than left to a full
-- table scan every time marketing runs a report.
-- ------------------------------------------------------------
CREATE INDEX idx_sales_date        ON sales(sale_date);
CREATE INDEX idx_sales_dealer      ON sales(dealer_id);
CREATE INDEX idx_vehicles_model    ON vehicles(model_id);
CREATE INDEX idx_models_brand      ON models(brand_id);
CREATE INDEX idx_models_platform   ON models(platform_id);
CREATE INDEX idx_vehicle_parts_part_date ON vehicle_parts(part_id, install_date);
