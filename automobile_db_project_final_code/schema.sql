-- Automobile Company Database — relational schema (MySQL)
--
-- Maps directly onto the accompanying ER diagram: every strong
-- entity became a table, every 1:M relationship became a foreign
-- key on the "many" side, and every M:N relationship (plant<->model,
-- dealer<->brand, model<->part) became its own junction table.
--
-- Run this with:  mysql -u <user> -p automobile_db < schema.sql
-- (create the database first: CREATE DATABASE automobile_db;)
-- db.py's init_db() runs this same file programmatically, so the
-- CLI and the Python path always build an identical schema.

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS locator_inquiries, vehicle_parts, model_parts,
    plant_models, dealer_brands, sales, vehicles, parts, models,
    platforms, customers, dealers, suppliers, plants, brands;

SET FOREIGN_KEY_CHECKS = 1;

-- A company (this whole DB) owns several brands, e.g. GM ->
-- Chevrolet, Buick, Cadillac, GMC.
CREATE TABLE brands (
    brand_id    INT AUTO_INCREMENT PRIMARY KEY,
    brand_name  VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- Resolves badge engineering: two distinct (brand, model) rows that
-- are, underneath, the same vehicle (same plant, same parts, same
-- underlying platform). A superclass/subclass relationship has no
-- native SQL construct, so the shared concept is promoted to its
-- own table here, and each models row points back up to it. Two
-- models sharing a platform_id ARE the badge-engineered pair.
CREATE TABLE platforms (
    platform_id     INT AUTO_INCREMENT PRIMARY KEY,
    platform_name   VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- Each brand offers several models, each with a body style
-- (4-door, wagon, coupe, convertible...). body_style lives directly
-- on the model row rather than as its own weak entity, since no
-- variant needs independent attributes beyond what's tracked here.
-- platform_id is nullable by design: most models stand alone with
-- no badge-engineered sibling.
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

-- Some plants do final assembly; others just supply parts. Which
-- models a plant assembles is tracked via plant_models below.
CREATE TABLE plants (
    plant_id    INT AUTO_INCREMENT PRIMARY KEY,
    plant_name  VARCHAR(150) NOT NULL,
    address     VARCHAR(255),
    plant_type  ENUM('assembly', 'parts', 'both') NOT NULL
) ENGINE=InnoDB;

-- Which plant(s) assemble which model(s). Many-to-many: badge-
-- engineered siblings on the same platform typically share a plant;
-- a plant might assemble several models.
CREATE TABLE plant_models (
    plant_id    INT NOT NULL,
    model_id    INT NOT NULL,
    PRIMARY KEY (plant_id, model_id),
    FOREIGN KEY (plant_id) REFERENCES plants(plant_id),
    FOREIGN KEY (model_id) REFERENCES models(model_id)
) ENGINE=InnoDB;

-- Suppliers supply certain parts for certain models. This pair of
-- tables (plus vehicle_parts, further down) is what makes a
-- defective-part traceability query answerable.
CREATE TABLE suppliers (
    supplier_id     INT AUTO_INCREMENT PRIMARY KEY,
    supplier_name   VARCHAR(150) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- supplying_plant_id is a single column rather than a separate
-- supplier_plants junction table: this project only ever needs to
-- isolate one plant per part (e.g. "the defective transmissions all
-- came from one of Getrag's plants"), so a single FK is enough.
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

-- A dealer may not carry every brand, so dealer_brands is a
-- junction table for "which brands this dealer carries." Defined
-- before vehicles, since vehicles.current_dealer_id references it.
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

-- Each vehicle has a made-up VIN (no real checksum needed). Which
-- specific part (with an install date) went into a specific VIN is
-- tracked via vehicle_parts below — the difference between "this
-- MODEL can use a Getrag transmission" (model_parts) and "this
-- exact CAR got one, installed on this date" (vehicle_parts); only
-- the latter can answer a recall-style query.
--
-- asking_price is separate from the eventual sale_price recorded in
-- sales: a vehicle in inventory has a listed price before any
-- customer agrees to a (possibly negotiated) final price at sale
-- time, so keeping them separate lets /search show honest pre-sale
-- pricing without faking a sale that hasn't happened.
CREATE TABLE vehicles (
    vin                     VARCHAR(17) PRIMARY KEY,
    model_id                INT NOT NULL,
    color                   VARCHAR(50),
    engine                  VARCHAR(50),
    transmission            VARCHAR(50),
    asking_price            DECIMAL(12,2),              -- pre-sale listed price
    manufacture_date        DATE,
    manufacturing_plant_id  INT,                         -- where THIS car was assembled
    current_dealer_id       INT,                         -- which dealer currently holds it
    arrived_at_dealer_date  DATE,                        -- when THIS car reached that lot
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

-- Individual buyers only (no corporate fleet buyers for this project).
CREATE TABLE customers (
    customer_id     INT AUTO_INCREMENT PRIMARY KEY,
    full_name       VARCHAR(150) NOT NULL,
    address         VARCHAR(255),
    phone           VARCHAR(30),
    gender          ENUM('M', 'F', 'Other', 'Prefer not to say'),
    annual_income   DECIMAL(12,2)
) ENGINE=InnoDB;

-- The core fact table: one row = one vehicle sold, at one dealer,
-- to one customer, on one date, for one price. Powers nearly every
-- required query.
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

-- Every search a dealer runs through /locator gets logged here (see
-- app.py), so marketing has something concrete to review, separate
-- from the required OLAP queries against actual sales.
CREATE TABLE locator_inquiries (
    inquiry_id  INT AUTO_INCREMENT PRIMARY KEY,
    brand       VARCHAR(100),
    model       VARCHAR(100),
    color       VARCHAR(50),
    body_style  VARCHAR(50),
    searched_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Indexed since these columns get filtered/grouped on constantly by
-- the required queries, rather than left to a full table scan.
CREATE INDEX idx_sales_date        ON sales(sale_date);
CREATE INDEX idx_sales_dealer      ON sales(dealer_id);
CREATE INDEX idx_vehicles_model    ON vehicles(model_id);
CREATE INDEX idx_models_brand      ON models(brand_id);
CREATE INDEX idx_models_platform   ON models(platform_id);
CREATE INDEX idx_vehicle_parts_part_date ON vehicle_parts(part_id, install_date);
