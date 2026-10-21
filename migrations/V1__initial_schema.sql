CREATE TABLE portfolios (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT portfolios_code_unique UNIQUE (code),
    CONSTRAINT portfolios_code_nonempty
        CHECK (BTRIM(code) <> ''),
    CONSTRAINT portfolios_name_nonempty
        CHECK (BTRIM(name) <> '')
);

CREATE TABLE loans (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id BIGINT NOT NULL,
    reference TEXT NOT NULL,
    principal_cents BIGINT NOT NULL,
    annual_rate_bps INTEGER NOT NULL,
    term_months INTEGER NOT NULL,
    first_payment_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT loans_portfolio_fk
        FOREIGN KEY (portfolio_id)
        REFERENCES portfolios (id)
        ON DELETE RESTRICT,

    CONSTRAINT loans_reference_unique
        UNIQUE (portfolio_id, reference),

    CONSTRAINT loans_reference_nonempty
        CHECK (BTRIM(reference) <> ''),

    CONSTRAINT loans_principal_positive
        CHECK (principal_cents > 0),

    CONSTRAINT loans_rate_nonnegative
        CHECK (annual_rate_bps >= 0),

    CONSTRAINT loans_term_positive
        CHECK (term_months > 0)
);

-- Projected installments computed from the loan terms
CREATE TABLE scheduled_cashflows (
    loan_id BIGINT NOT NULL,
    payment_number INTEGER NOT NULL,
    due_date DATE NOT NULL,
    principal_cents BIGINT NOT NULL,
    interest_cents BIGINT NOT NULL,
    remaining_balance_cents BIGINT NOT NULL,

    CONSTRAINT scheduled_cashflows_pk
        PRIMARY KEY (loan_id, payment_number),

    CONSTRAINT scheduled_cashflows_loan_fk
        FOREIGN KEY (loan_id)
        REFERENCES loans (id)
        ON DELETE RESTRICT,

    CONSTRAINT scheduled_cashflows_due_date_unique
        UNIQUE (loan_id, due_date),

    CONSTRAINT scheduled_cashflows_payment_positive
        CHECK (payment_number > 0),

    CONSTRAINT scheduled_cashflows_principal_nonnegative
        CHECK (principal_cents >= 0),

    CONSTRAINT scheduled_cashflows_interest_nonnegative
        CHECK (interest_cents >= 0),

    CONSTRAINT scheduled_cashflows_balance_nonnegative
        CHECK (remaining_balance_cents >= 0)
);
