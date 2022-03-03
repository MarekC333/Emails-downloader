import os
import imaplib
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from unidecode import unidecode     # decoding
from urllib.parse import unquote    # decoding


user = os.getenv("GMAIL_USER")
password = os.getenv("GMAIL_PASSWORD")
imap_url = "imap.gmail.com"
search_in_INBOX = 'unicreditbank@unicreditgroup.sk'
table = 'bankove_prevody2'


conn=psycopg2.connect(
    host=os.getenv("POSTGRES_HOST"),
    port=5432,
    database=os.getenv("POSTGRES_DATABASE"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"))

def search(key, value, con):
    _, data = con.search(None,key,'"{}"'.format(value))
    return data

def data_loading():
    
    dat = str_email.find('Datum:')
    date_of_transaction = ((str_email[dat+7:dat+23]).replace('T',' ')).replace('-','.')
    if dat == -1:
        dat = str_email.find('tum:')
        date_of_transaction = ((str_email[dat+5:dat+21]).replace('T',' ')).replace('-','.')

    

    amount = str_email.find('Suma: ')
    end_of_am = str_email[amount:amount+20].find('EUR')
    try:
        transaction_amount = (int((str_email[amount+6:amount
        +end_of_am-1]).replace('.','').replace(',','')))/100
    except Exception:
        if amount == -1: transaction_amount = 0

    description = str_email.find('Popis: ')
    end_of_description = str_email[description:description+120].find('Aktu')
    # dekodovanie textu s diakritikou:
    transaction_description = unidecode(unquote((str_email[
        description+7:description+end_of_description-1]).replace('=','%')))
    if description == -1:
        description = str_email.find('Nazov uctu protistrany')
        end_of_description = str_email[description:description+200].find('Aktu')
        transaction_description = unidecode(unquote((str_email[
            description+24:description+end_of_description-7]).replace('=','%')))
    if end_of_description == -1:
        end_of_description = str_email[description:description+120].find('Disponibil')
        # dekodovanie textu s diakritikou:
        transaction_description = unidecode(unquote((str_email[
            description+7:description+end_of_description-1]).replace('=','%')))
    if description == -1:
        if str_email.find('cia o zostatku') != -1: transaction_description = 'Informácia o zostatku'
        elif str_email.find('cia o transakcii'): 
            transaction_description = 'Informácia o transakcii'

    balance = str_email.find('zostatok')
    end_of_balance = str_email[balance:balance+110].find('EUR')
    current_balance = ([int(n) for n in ((str_email[balance+13:balance+130])
        .replace('.','').replace(',','')).split() if n.isdigit()])[-1]/100

    if end_of_balance == -1:
        end_of_balance = str_email[balance:balance+200].find('EUR')
        current_balance = ([int(n) for n in ((str_email[balance+13:balance+end_of_balance-1])
            .replace('.','').replace(',','')).split() if n.isdigit()])[-1]/100

    if transaction_amount > 0: inout = 'Prichádzajúca suma'
    elif transaction_amount == 0: inout = 'Žiaden pohyb na účte'
    else: inout = 'Odchádzajúca suma'

    with conn, conn.cursor() as cur:
        insert_data = sql.SQL("INSERT INTO {tab} (id_emailu, datum, druh_transakcie, suma, popis, zostatok)\
            VALUES ({i}, {date_of_transaction}, {inout}, {transaction_amount}, {transaction_description}, {current_balance})").format(
                tab=sql.Identifier(table),
                i=sql.Literal(i),
                date_of_transaction=sql.Literal(date_of_transaction),
                inout=sql.Literal(inout),
                transaction_amount=sql.Literal(transaction_amount),
                transaction_description=sql.Literal(transaction_description),
                current_balance=sql.Literal(current_balance)
        )
        
        cur.execute(insert_data)
def last_update():


    select_sql=sql.SQL(
        '''
        SELECT id_emailu
        FROM {tab}
        ORDER BY id_emailu DESC
        LIMIT 1
        '''
    ).format(
        tab=sql.Identifier(table)
        )
    cursor=conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(select_sql)  # vyvolanie
    
    last_update_data = cursor.fetchall()[0][0] 
    return last_update_data

if __name__ == "__main__":    
    con = imaplib.IMAP4_SSL(imap_url)   # zabezpecenie
    con.login(user, password)
    con.select("INBOX", readonly=True)
    print('')
    print(f'{" gmail.com conected ":*^60}')

    emails_id = list(map(int, (((str(search(
        'FROM', search_in_INBOX, con)))[3:-2]).replace(' ',', ')).split(',')))
    searched_emails = len(emails_id)


    last_update()

    number_of_updates = 0
    excluded = []
    transaction_confirmation = []
    transaction_to_update = len(emails_id[emails_id.index(last_update())+1:searched_emails])
    
    found = (f' I found {transaction_to_update} new transactions')
    #print(f'{found:*^60}')
    if transaction_to_update: 
        print(f'{found:*^60}')
        print(f'{" Table will be updated ":*^60}')
        print('')
    else:
        print('')

    # prechadzanie viacerych mailov podla rozsahu id
    for i in emails_id[emails_id.index(last_update())+1:searched_emails]:
        try:
            ids = (f' id unicredit emailu: {str(emails_id.index(i))} *** id v gmail.com: {str(i)} ')
            print(f' {ids:*^60} ')
            ib = str(i).encode('UTF-8') # enkodovanie str to bytes
            _, data = con.fetch(ib,'(RFC822)')
            str_email = (data[0][1]).decode('UTF-8')    
            data_loading()
            number_of_updates += 1
        except Exception as e:
            if str_email.find('potvrdenie o transakcii') != -1: transaction_confirmation.append(i)
            else: excluded.append(i)

if number_of_updates == 0: print(f'{" The table was up to date, no update was required ":*^60}')
else: 
    pocet_updatovanych = (f' Number of new transakctions: {number_of_updates} ')
    print(f'{" update is complete ":*^60}')

conn.close()
print((f'{" Connection closed ":*^60}'))