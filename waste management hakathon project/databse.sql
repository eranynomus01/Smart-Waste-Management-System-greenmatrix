USE wastemanagementmain;
ALTER TABLE complaint
ADD COLUMN assigned_staff_name VARCHAR(100) AFTER assigned_to;

