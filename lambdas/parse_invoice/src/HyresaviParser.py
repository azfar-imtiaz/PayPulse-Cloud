import re

import textract
from datetime import datetime
from typing import Dict, Union, NoReturn, Tuple
from logging_config import logger


def extract_text_from_pdf(filename) -> Union[str, NoReturn]:
    """
    Extract text from PDF file using Textract
    :param filename: The path to the PDF file
    :return: A string containing the full text of the document
    """
    try:
        text = textract.process(filename).decode()
        logger.info(f"Text extracted from {filename}: \n\n{text}")
        return text
    except Exception as e:
        logger.error(f"The following error occurred during text extraction: {str(e)}")
        raise e


def is_line_viktig(line: str) -> Tuple[bool, str]:
    """
    This function checks if the line's text contains any of the key header fields or only numbers
    :param line: The line currently being processed in the PDF file
    :return: A bool indicating whether the line should be stored or not, and the (possibly processed)
    line itself
    """
    categories = ["hyra", "kallvatten", "varmvatten", "el enligt", "mervärdesskatt"]
    line_lowercase = line.lower()
    if any(cat in line_lowercase for cat in categories):
        if line_lowercase.startswith("kallvatten"):
            return True, "Kallvatten"
        elif line_lowercase.startswith("varmvatten"):
            return True, "Varmvatten"
        elif line_lowercase.startswith("el enligt"):
            return True, "El"
        else:
            return True, line
    # if line contains only numbers
    elif line.replace(' ', '').replace('*', '').isdigit():
        return True, line
    return False, ""


def parse_line(line: str) -> str:
    return re.sub(r'[*()]', '', line).strip()


def convert_date_format(date_text: str) -> Dict:
    try:
        datetime_obj = datetime.strptime(date_text, '%Y-%m-%d')
        return {
            'Due Date': datetime_obj.strftime('%d-%m-%Y'),
            'due_date_month': datetime_obj.month,
            'due_date_year': datetime_obj.year
        }
    except:
        return {
            'Due Date': date_text
        }


def extract_rental_info(text: str) -> Union[Dict, NoReturn]:
    extracted_info = dict()
    regexes = {
        'OCR': r'(\d{10}) #',
        'Due Date': r'Förfallodatum: (\d{4}-\d{2}-\d{2})',
        'Total Amount': r'Totalt att betala:\n\n([\d ]+)'
    }

    try:
        logger.info("Parsing invoice...")
        logger.info("\tRunning regexes...")
        for title, rg in regexes.items():
            m = re.search(rg, text)
            if m:
                extracted_value = m.group(1)
                # Replace space with comma in the total amount, make it look cleaner
                if title == 'Total Amount':
                    extracted_value = extracted_value.replace(' ', ',')
                    extracted_info[title] = extracted_value
                elif title == 'Due Date':
                    # get the parsed date as string, due date month, and due date year
                    due_date_dict = convert_date_format(extracted_value)
                    # store all values in dict
                    extracted_info.update(due_date_dict)
                else:
                    extracted_info[title] = extracted_value

        rental_breakdown = []
        start_storing = False
        logger.info("\tLooping over text...")
        for line in text.split('\n'):
            if line.find("Hyra") >= 0:
                start_storing = True

            if line.find("Förfallodatum") >= 0:
                # start_storing = False
                break

            viktig_status, header = is_line_viktig(line)
            if start_storing and viktig_status:
                rental_breakdown.append(header)
            elif line.find("Moms:") >= 0:
                # this information is present in a single line, like this: "Moms: 173"
                components = [parse_line(x) for x in line.split(':')]
                extracted_info[components[0]] = components[1]

        logger.info(f"Rental breakdown: {rental_breakdown}")
        assert len(rental_breakdown) % 2 == 0
        rental_breakdown_mid = int(len(rental_breakdown) / 2)

        for index in range(rental_breakdown_mid):
            parsed_key = parse_line(rental_breakdown[index])
            parsed_value = parse_line(rental_breakdown[index + rental_breakdown_mid])
            # Replace space with comma in the rent value, to make it look cleaner
            if parsed_key == 'Hyra':
                parsed_value = parsed_value.replace(' ', ',')
            extracted_info[parsed_key] = parsed_value

        return extracted_info
    except AssertionError:
        raise AssertionError("Assertion failed - got something extra or missing!")
    except Exception as e:
        raise e


def extract_rental_info_from_file(filename) -> Dict:
    text = extract_text_from_pdf(filename)
    extractions = extract_rental_info(text)
    # store only the filename, not the whole path
    extractions['Filename'] = filename.split('/')[-1].split('.')[0]
    return extractions


'''
if __name__ == '__main__':
    filename = "/Users/azfarimtiaz/PythonProjects/Email-extractor/attachments/rental_invoices/Hyresavi_1297534008.pdf"
    extractions = extract_rental_info_from_file(filename)
    print(extractions)
'''