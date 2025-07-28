from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

def get_conversation_chain(vectorstore, document_id: int = None, learned_context_section=""):
    """Creates a conversation chain for question answering with dynamic learned context injection."""
    
    llm = ChatOpenAI(temperature=0.2, model="gpt-4")
    # Use standard retriever
    retriever = vectorstore.as_retriever(search_kwargs={'k': 5})

    # Create a unified template that handles both regular context and learned context
    template = """You are an AI assistant that answers questions based on the provided document context.
Use the context below to answer the question. If you don't know the answer, just say that you don't know.

RULES:
1. Learned Context override the context.
2. If a Learned Context includes a correction or detail, you MUST use it and reflect it in your answer.
3. Only use context to support or extend Learned Context Answers.
4. If no Learned Context is relevant, fall back to context.

Learned Context: {learned_context_section}

Context: {context}

Question: {question}

Answer:"""

    # Create prompt template with learned_context_section as a variable
    custom_prompt = PromptTemplate(
        input_variables=["context", "question"],
        template=template
    )
    
    # Create a custom wrapper that handles the learned context injection
    class LearnedContextRetrievalQA:
        def __init__(self, retriever, llm, prompt, learned_context_section=""):
            self.retriever = retriever
            self.llm = llm
            self.prompt = prompt
            self.learned_context_section = learned_context_section
            
        def invoke(self, inputs):
            # Get the query from inputs
            query = inputs.get("query", inputs.get("question", ""))
            learned_section = inputs.get("learned_context_section", self.learned_context_section)
            
            # Retrieve relevant documents using modern invoke method
            docs = self.retriever.invoke(query)
            
            # Format context from retrieved documents
            context = "\n\n".join([doc.page_content for doc in docs])
            
            # Create the formatted prompt
            formatted_prompt = self.prompt.format(
                context=context,
                question=query,
                learned_context_section=learned_section
            )
            
            # Get response from LLM
            response = self.llm.invoke(formatted_prompt)
            
            # Format response similar to RetrievalQA
            return {
                "result": response.content,
                "source_documents": docs
            }
    
    # Create and return the custom chain
    conversation_chain = LearnedContextRetrievalQA(
        retriever=retriever,
        llm=llm,
        prompt=custom_prompt,
        learned_context_section=learned_context_section
    )
    
    return conversation_chain
