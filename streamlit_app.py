import openai
import sys
import json
import neo4j

from neo4j import GraphDatabase
from neo4j.exceptions import CypherSyntaxError


# Neo4j 연결 정보 설정
uri = "neo4j+s://ff4716af.databases.neo4j.io:7687"
username = "neo4j"
password = "zuHXwqosP3t5rJBJkbQjxGRmgIDtGyq0FiAjbi9gwAM"

# Neo4j 드라이버 초기화
driver = GraphDatabase.driver(uri, auth=(username, password))

# LLM(OpenAI) API 키 설정
openai_api_key = openai_api_key

node_properties_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE NOT type = "RELATIONSHIP" AND elementType = "node"
WITH label AS nodeLabels, collect(property) AS properties
RETURN {labels: nodeLabels, properties: properties} AS output
"""

rel_properties_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE NOT type = "RELATIONSHIP" AND elementType = "relationship"
WITH label AS nodeLabels, collect(property) AS properties
RETURN {type: nodeLabels, properties: properties} AS output
"""

rel_query = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE type = "RELATIONSHIP" AND elementType = "node"
RETURN {source: label, relationship: property, target: other} AS output
"""


def schema_text(node_props, rel_props, rels):
    return f"""
  This is the schema representation of the Neo4j database.
  Node properties are the following:
  {node_props}
  Relationship properties are the following:
  {rel_props}
  Relationship point from source to target nodes
  {rels}
  Make sure to respect relationship types and directions
  """


class Neo4jGPTQuery:
    def __init__(self, url, user, password, openai_api_key):
        self.driver = GraphDatabase.driver(url, auth=(user, password))
        openai.api_key = openai_api_key

        self.schema = self.generate_schema()
        self.conversation_history = []
        print("check history \n",self.conversation_history)

    def generate_schema(self):
        node_props = self.query_database(node_properties_query)
        rel_props = self.query_database(rel_properties_query)
        rels = self.query_database(rel_query)
        return schema_text(node_props, rel_props, rels)

    def refresh_schema(self):
        self.schema = self.generate_schema()

    @property
    def get_system_message(self):


        custom_prompt = str([[{"role": "user", "content": "Tell me about books related to Art"},
                              {"role": "agent","content": "MATCH(b:Book)-[:HAS_SUBJECT]->(s:SubjectDetail) MATCH(b:Book)-[:HAS_SUBJECT]->(s:SubjectDetail) WHERE ANY(item IN [s.Subject, s.Group3] WHERE toLower(item) CONTAINS 'art' OR toLower(item) CONTAINS '예술') RETURN b,s limit 5"},
]
                             ])

        return f"""

        Task: Generate Cypher queries to retrieve information from a Neo4j Graph Database based on user requests about books.

        Instructions:
        - Your role is to assist users by formulating Cypher queries to find specific information about books.
        - When querying a node, retrieve all available properties of the node to provide comprehensive information.
        - Use 'CONTAINS' for string comparison to ensure broad matching; avoid using exact equality unless requested.
        - Do not use Grammar "EXISTS".
        - Do not disclose sensitive identifiers like Person IDs.
        - Aim to provide a diverse set of results; for ranking questions, unless specified, present the results in a randomized order.
        - Limit the results to a reasonable number to avoid overwhelming the user.
        - Keep in mind the database schema and available properties for each node type.
        - Refer to past interactions for context and ensure consistency in responses.
        
        Note: Remember that some properties like Barcode, MMS_Id, and PubYear are integers. 
              Avoid using quotation marks for these values in your queries.

        Example:
            User: "Show me a book about 'Ancient Rome'."
            Agent: "MATCH(b:Book)-[:HAS_SUBJECT]->(s:SubjectDetail) WHERE s.Subject CONTAINS 'Ancient Rome' RETURN b ORDER BY b.Pub_Year DeSC LIMIT 1"


         Custom prompt: {custom_prompt} 
         Schema:{self.schema}
         History:{self.conversation_history}
          
            """

    def query_database(self, neo4j_query, params={}):
        with self.driver.session() as session:
            result = session.run(neo4j_query, params)
            output = [dict(r) for r in result]

            return output

    def construct_cypher(self, question, history=None):

        messages = [
            {"role": "system", "content": self.get_system_message},
            {"role": "user", "content": question},
        ]

        if history:
            for entry in history:

                messages.append({"role": "user", "content": entry["question"]})
                for result in entry["results"]:

                    if isinstance(result, dict):
                        result = json.dumps(result)
                    messages.append({"role": "assistant", "content": result})
            #messages.extend(history)

        completions = openai.ChatCompletion.create(
            model='gpt-3.5-turbo-16k',
            temperature=0.0,
            max_tokens=800,
            messages=messages
        )

        responses = completions.choices[0].message.content.split(';')
        messages.append({"role": "agent", "content": responses[-1]})

        return responses, messages

    # def natural_language_response(self, data, creativity_level, conversation_history = None):
    #     if isinstance(data,(dict, list)):  # data가 리스트 형태 등인 경우 수정이 필요함
    #         data = json.dumps(data)  # JSON 문자열로
    #     #user_input
    #     #print(data)
    #     print("\n")
    #     custom_prompt = """
    #         Task: Generate a natural language response based on the query results from a Neo4j Graph Database concerning books, which can include both general bibliographic data and contextual information upon request.
    #
    # Instructions:
    # - Start by providing a clean, concise natural language summary of the general bibliographic data retrieved from the database.
    # - If the user requests more details, distinguish between:
    #  (1) Simple bibliographic information, such as publication date, edition, ISBN, etc.
    #  (2) Contextual information, which might include the book's relevance, its significance within a certain field, the popularity among the library's patrons, or other cultural or academic considerations.
    #
    # - When presenting data, maintain the integrity of the information provided by the Cypher query results. Do not alter or misinterpret the factual content.
    # - While formulating responses, especially for contextual details, make logical inferences based on the data. For instance:
    # - Discuss the target audience or academic value of the book if pertinent.
    # - Deduce the possible reason for the acquisition timing of the book by the library, comparing it to publication dates and known academic cycles.
    # - If available, analyze borrowing patterns to infer the book's popularity or relevance during certain periods.
    #
    # - Your response should be informative yet engaging, providing insight into the data that goes beyond mere facts.
    #
    # Note: Ensure that the response respects the privacy of any individuals and does not disclose sensitive information. Keep the conversation history in mind to provide a consistent and coherent experience.
    #
    # Custom prompt example:
    # User: "I want to know more about this book, can you tell me its historical and cultural significance?"
    # Agent: "Based on the data, 'The Great Gatsby' by F. Scott Fitzgerald, published in 1925, not only depicts the flamboyance and excess of the Jazz Age but also offers a critical portrayal of the American Dream.
    #         Its reception was modest at first, but the novel experienced a resurgence in popularity during World War II. The book has since become a staple in American literature courses and is considered a literary classic."
    #         """
    #
    #     messages = [
    #         {"role": "system", "content": custom_prompt},
    #         {"role": "user", "content": data},
    #
    #     ]
    #
    #     completions = openai.ChatCompletion.create(
    #         model='gpt-3.5-turbo', #gpt-4가능?
    #         temperature=creativity_level,
    #         max_tokens=800,
    #         messages=messages
    #     )
    #     return completions.choices[0].message.content

    def natural_language_response_basic(self, data, creativity_level): #기본 서지 정보

        if isinstance(data, (dict, list)):
            data_str = json.dumps(data)
        else:
            data_str = str(data)

        basic_prompt = """
        Provide a concise summary of the book's bibliographic information in natural language based on the data provided.
        """
        messages = [
            {"role": "system", "content": basic_prompt},
            {"role": "user", "content": data_str},
        ]

        response = openai.ChatCompletion.create(
            model='gpt-3.5-turbo', # 이정도면 4를 써도 되는 걸까?
            temperature=creativity_level,
            max_tokens=500,
            messages=messages
        )
        print ("\n")
        print("Bibliographic information")
        print("\n")
        return response.choices[0].message['content']

    def natural_language_response_detailed(self, data, creativity_level, conversation_history) :

        previous_questions = [entry['question'] for entry in conversation_history]
        #conversation_history에서의 마지막 질문과 이전의 대답 추출
        previous_answers = [entry['results'] for entry in conversation_history]
        last_question = previous_questions[-1] if previous_questions else ""
        last_answers = previous_answers[-1] if previous_answers else {}

        # JSON 형식으로 데이터 변환
        if isinstance (data, (dict, list)) :
            data_str = json.dumps (data)
        else :
            data_str = str (data)

        # # 맥락 정보를 포함
        # detailed_context = self.analyze_user_query_for_context (last_question, previous_answers, data)
        # detailed_response = self.create_detailed_response (detailed_context, creativity_level)


        # if isinstance (detailed_response, (dict, list)) :
        #     detailed_response_str = json.dumps (detailed_response)   # GPT 모델을 사용하여 자연어로 상세한 응답 생성
        # else :
        #     detailed_response_str = str (detailed_response)

        custom_prompt = f"""
        Task: Generate a natural language response that provides bibliographic and contextual information about a book upon user's request. 
              The response should integrate bibliographic details with broader contextual insights 
              based on the user's previous question '{last_question}' and your knowledge of bibliographic and contextual data.

        Instructions:
        - Start by offering a clear and concise summary of the bibliographic information such as the title, author, publisher, and publication year.
        - If the user requests more detailed information, explore the following areas:

          1) Key Features of the Book:
             Identify the book's primary audience and its intended use. For example, if it's a guidebook for graduate students on academic writing and essay composition, infer that its main target audience could be prospective graduate students or readers seeking help in academic writing.

          2) Historical Context of the Record:
             Analyze the book's publication and acquisition dates. If a book was published in 2012 and acquired by the library in August 2014, one might infer that there was a high demand for this book post-publication, potentially aligned with the graduate admission season. Cross-examine other books published around 2012 to discern prevalent themes or subjects that were prominent in academia or society at that time.

          3) Geographical and Cultural Context:
             Consider the place of publication and the publisher. If the book was published by Ten Speed Press in California, Berkeley, you can search for other works published by the same press or at the same location. Identifying the types of subjects commonly published by them can reveal the publisher's specialty or focus.

          4) Popularity and Usage Trends:
             Examine borrowing patterns, such as checkouts, renewals, and returns, to gauge the book's popularity and usage over time. Books that are frequently checked out or renewed may indicate a longer reading or usage period, suggesting a deep engagement with the content.

        Your response should be informative, engaging, and provide insight that extends beyond mere factual representation. Ensure it respects individual privacy and does not disclose sensitive information. Maintain consistency with the conversation history for a coherent user experience.

        Example of a custom prompt for a user's question about 'The Great Gatsby':
        User: "Can you tell me about the historical and cultural significance of 'The Great Gatsby'?"
        Agent: "Published in 1925 by F. Scott Fitzgerald, 'The Great Gatsby' is not only a vivid depiction of the Jazz Age but also a critical commentary on the American Dream. Its initial reception was moderate, but the novel saw a resurgence in popularity during WWII and has since become an integral part of American literature and a classic in the canon."
        """

        messages = [
            {"role" : "system", "content" : custom_prompt},
            {"role" : "user", "content" : data_str},
        ]

        response = openai.ChatCompletion.create (
            model='gpt-3.5-turbo',
            temperature=creativity_level,
            max_tokens=500,
            messages=messages
        )
        detailed_response = response.choices[0].message['content']
        print("Detailed context response:")
        print("\n")
        print(detailed_response)
        return detailed_response

    def run(self, question, creativity_level, history=None, retry=True):
        # Construct Cypher statements
        cyphers, messages = self.construct_cypher(question, history)

        # Execute queries and process results
        results = []
        for cypher in cyphers:
            print("Executing Cypher Query:", cypher.strip())
            try:
                query_result = self.query_database(cypher.strip())

                printable_results = self.process_results(query_result)
                for printable_result in printable_results:
                    print("Query Result:", printable_result)

                    # Append the current question and its results to the conversation history
                self.conversation_history.append({'question': question, 'results': printable_results})
                # for entry in self.conversation_history:
                #     print(entry)
                results.extend(printable_results)


            except CypherSyntaxError as e:
                print("Cypher Syntax Error")
                if not retry:
                    return "Invalid Cypher syntax. Unable to process the query."
                re_question = input("Please provide more specific information: ")
                if re_question.lower() in ["exit", "quit", "종료"]:
                    print("Exiting program...")
                    sys.exit()
                # Retry with corrected information
                return self.run(re_question, creativity_level, self.conversation_history, False)

        if len(self.conversation_history) > 5:
            self.conversation_history = self.conversation_history[-5:]

        if results:
            all_results_str = "\n".join(map(str, results))
            nl_response = self.natural_language_response_basic(all_results_str, creativity_level)
            print(nl_response)
            print("-------------------------")
            # Ask for additional information based on the results
            follow_up_ask= "Would you like to know anything more specific based on these results?"
            print(follow_up_ask)
            user_follow_up_input = input("Your response(yes/no): ")

            # Handle additional follow-up response
            if user_follow_up_input.lower() == 'yes':
                follow_up_question = input("What specific information are you looking for?: ")

                # Here we call run recursively, which will process the follow-up question
                follow_up_results = self.run(follow_up_question, creativity_level, self.conversation_history)

                # After getting the follow-up results, we append the follow-up question and its results to the history
                if follow_up_results:
                    detailed_response = self.natural_language_response_detailed(follow_up_results,creativity_level)
                    print(detailed_response)
                    self.conversation_history.append({'question': follow_up_question, 'results': follow_up_results})
                    # for entry in self.conversation_history:
                    #     print(entry)
                    # Limit the conversation history to the last 5 interactions
                    if len(self.conversation_history) > 5:
                        self.conversation_history = self.conversation_history[-5:]

                return follow_up_results
            else:
                return nl_response
        return results

    def process_results(self, query_result):
        printable_results = []
        for record in query_result:
            # Convert each record to a dictionary
            printable_record = {key: self.convert_to_dict(value) for key, value in record.items()}
            printable_results.append(printable_record)
        return printable_results

    def convert_to_dict(self, obj):
        if isinstance(obj, neo4j.graph.Node) or isinstance(obj, neo4j.graph.Relationship):
            return {**obj}
        elif isinstance(obj, list):
            return [self.convert_to_dict(item) for item in obj]
        return obj
def get_creativity_level():
        while True:
            try:
                creativity_level = int(
                    input("Set the creativity level(1-10, where 1 is most literal and 10 is most creative): "))
                if 1 <= creativity_level <= 10:
                    return(creativity_level - 1) / 9.0
                else:
                    print("Please enter a number between 1 and 10.")
            except ValueError:
                print("Invalid input. Please enter a numerical value.")

if __name__ == "__main__":
        book_db = Neo4jGPTQuery(
            url="neo4j+s://ff4716af.databases.neo4j.io",
            user="neo4j",
            password="zuHXwqosP3t5rJBJkbQjxGRmgIDtGyq0FiAjbi9gwAM",
            openai_api_key=openai_api_key,
        )

        creativity_level = get_creativity_level()

        while True:
            user_input = input("Please fill out the book information you want.('exit' for exit):")
            if user_input.lower() in ["exit", "quit", "종료"]:
                print("Exiting program...")
                break
            book_db.run(user_input, creativity_level=creativity_level)
