def remove_spaces_from_file():
    filename = input("Enter the name of the .txt file: ")

    try:
        with open(filename, 'r') as file:
            lines = file.readlines()

        # Remove all spaces from each line
        cleaned_lines = [line.replace(" ", "") for line in lines]

        # Optionally, save to a new file or overwrite
        with open(filename, 'w') as file:
            file.writelines(cleaned_lines)

        print(f"Spaces removed successfully from '{filename}'.")

    except FileNotFoundError:
        print(f"File '{filename}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    remove_spaces_from_file()
