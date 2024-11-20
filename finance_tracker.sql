--ddl commands
CREATE TABLE category (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL
);

CREATE TABLE budget (
    budget_id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT,
    amount DECIMAL(10,2) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    FOREIGN KEY (category_id) REFERENCES category(category_id)
);

CREATE TABLE notification (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    message VARCHAR(255),
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read TINYINT(1) DEFAULT 0,
    budget_id INT,
    FOREIGN KEY (budget_id) REFERENCES budget(budget_id)
);

CREATE TABLE transaction (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT,
    amount DECIMAL(10,2) NOT NULL,
    transaction_type VARCHAR(50),
    description TEXT,
    transaction_date DATE NOT NULL,
    budget_id INT,
    FOREIGN KEY (category_id) REFERENCES category(category_id),
    FOREIGN KEY (budget_id) REFERENCES budget(budget_id)
);

--dml commands
INSERT INTO category (category_name) 
VALUES 
    ('Food'), 
    ('Transportation'), 
    ('Entertainment'), 
    ('Utilities'), 
    ('Healthcare');

INSERT INTO budget (category_id, amount, start_date, end_date) 
VALUES 
    (1, 2000.00, '2024-11-01', '2024-11-30'),
    (2, 1500.00, '2024-11-01', '2024-11-30'),
    (3, 1000.00, '2024-11-01', '2024-11-30'),
    (4, 500.00, '2024-11-01', '2024-11-30'), 
    (5, 1200.00, '2024-11-01', '2024-11-30');  

INSERT INTO transaction (category_id, amount, transaction_type, description, transaction_date, budget_id)
VALUES 
    (1, 250.00, 'expense', 'Groceries', '2024-11-05', 1),
    (1, 100.00, 'expense', 'Dining out', '2024-11-12', 1),
    (1, 150.00, 'expense', 'Takeout', '2024-11-20', 1);

INSERT INTO transaction (category_id, amount, transaction_type, description, transaction_date, budget_id)
VALUES 
    (2, 80.00, 'expense', 'Fuel', '2024-11-03', 2),
    (2, 50.00, 'expense', 'Bus fare', '2024-11-10', 2),
    (2, 100.00, 'expense', 'Car maintenance', '2024-11-18', 2);

INSERT INTO transaction (category_id, amount, transaction_type, description, transaction_date, budget_id)
VALUES 
    (3, 200.00, 'expense', 'Movie tickets', '2024-11-07', 3),
    (3, 300.00, 'expense', 'Concert', '2024-11-15', 3);

INSERT INTO transaction (category_id, amount, transaction_type, description, transaction_date, budget_id)
VALUES 
    (4, 150.00, 'expense', 'Electricity bill', '2024-11-01', 4),
    (4, 100.00, 'expense', 'Water bill', '2024-11-09', 4);

INSERT INTO transaction (category_id, amount, transaction_type, description, transaction_date, budget_id)
VALUES 
    (5, 300.00, 'expense', 'Doctor visit', '2024-11-05', 5),
    (5, 400.00, 'expense', 'Medication', '2024-11-18', 5);

INSERT INTO notification (message, budget_id) 
VALUES 
    ('Budget exceeded for category ID 1 by amount: Rs. 100.00', 1),
    ('Budget exceeded for category ID 2 by amount: Rs. 50.00', 2),
    ('Budget exceeded for category ID 3 by amount: Rs. 150.00', 3);

SELECT notification_id, message, sent_at
        FROM Notification
        WHERE is_read = FALSE
        ORDER BY sent_at DESC;

UPDATE Notification
        SET is_read = TRUE
        WHERE notification_id = %s;

--join and aggregate queries
SELECT c.category_name,
           SUM(CASE WHEN t.transaction_type = 'expense' THEN t.amount ELSE 0 END) AS total_expense,
           SUM(CASE WHEN t.transaction_type = 'income' THEN t.amount ELSE 0 END) AS total_income
    FROM Category c
    LEFT JOIN Transaction t ON c.category_id = t.category_id
         AND MONTH(t.transaction_date) = %s 
         AND YEAR(t.transaction_date) = %s
    GROUP BY c.category_id;

SELECT c.category_name, 
           IFNULL(SUM(b.amount), 0) AS total_budget,
           IFNULL(SUM(t.amount), 0) AS total_expense
    FROM Category c
    LEFT JOIN Budget b ON c.category_id = b.category_id
                        AND MONTH(b.start_date) <= %s 
                        AND MONTH(b.end_date) >= %s
                        AND YEAR(b.start_date) <= %s
                        AND YEAR(b.end_date) >= %s
    LEFT JOIN Transaction t ON c.category_id = t.category_id
                             AND t.transaction_type = 'expense'
                             AND MONTH(t.transaction_date) = %s
                             AND YEAR(t.transaction_date) = %s
    GROUP BY c.category_id;

SELECT 
            b.amount AS budget, 
            b.category_id, 
            COALESCE(SUM(t.amount), 0) AS total_expenses
        FROM 
            budget b
        LEFT JOIN 
            transaction t ON b.category_id = t.category_id
        WHERE 
            b.start_date < %s 
            AND YEAR(%s) <= YEAR(b.end_date) 
            AND MONTH(%s)+1 <= MONTH(b.end_date)
        GROUP BY 
            b.category_id, b.amount;



--stored procedure
--also has a nested query
DELIMITER $$

CREATE PROCEDURE CheckBudgetExceed(IN cat_id INT, IN trans_date DATE)
BEGIN
    DECLARE total_spent DECIMAL(10, 2);
    DECLARE budget_amount DECIMAL(10, 2);
    DECLARE exceed_amount DECIMAL(10, 2);
    DECLARE exceed_message VARCHAR(255);
    DECLARE budget_id INT;

    SET total_spent = CalculateMonthlyExpenditure(cat_id, MONTH(trans_date), YEAR(trans_date));

    SELECT b.amount, b.id INTO budget_amount, budget_id
    FROM (
        SELECT amount, id
        FROM Budget
        WHERE category_id = cat_id
              AND start_date <= trans_date
              AND end_date >= trans_date
        ORDER BY end_date DESC
        LIMIT 1
    ) AS b;

    IF budget_amount IS NOT NULL THEN
        SET exceed_amount = total_spent - budget_amount;
        SET exceed_message = CONCAT('Budget exceeded for category ID ', cat_id, ' by amount: Rs.', exceed_amount);

        IF total_spent > budget_amount THEN
            SELECT budget_id INTO budget_id
            FROM Budget
            WHERE category_id = cat_id
                  AND start_date <= trans_date
                  AND end_date >= trans_date
            ORDER BY end_date DESC
            LIMIT 1;

            INSERT INTO notification (message, budget_id)
            VALUES (exceed_message, budget_id);
        END IF;
    ELSE
        SET exceed_message = CONCAT('No budget found for category ID ', cat_id, ' on date: ', trans_date);
        INSERT INTO notification (message)
        VALUES (exceed_message);
    END IF;
END $$

DELIMITER ;


-- function
DELIMITER $$

CREATE FUNCTION CalculateMonthlyExpenditure(cat_id INT, month_val INT, year_val INT)
RETURNS DECIMAL(10, 2)
DETERMINISTIC
BEGIN
    DECLARE total DECIMAL(10, 2);
    
    SELECT SUM(amount) INTO total
    FROM Transaction
    WHERE category_id = cat_id 
          AND transaction_type = 'expense'
          AND MONTH(transaction_date) = month_val
          AND YEAR(transaction_date) = year_val;
    
    RETURN IFNULL(total, 0);
END $$

DELIMITER ;

--trigger
DELIMITER $$

CREATE TRIGGER AfterTransactionInsert
AFTER INSERT ON Transaction
FOR EACH ROW
BEGIN
    CALL CheckBudgetExceed(NEW.category_id, NEW.transaction_date);
END $$

DELIMITER ;
