import pytest
from unittest.mock import Mock, call, patch
from pydantic import BaseModel
import instructor
from atomic_agents import (
    BaseIOSchema,
    AtomicAgent,
    AgentConfig,
    BasicChatInputSchema,
    BasicChatOutputSchema,
)
from atomic_agents.context import ChatHistory, SystemPromptGenerator, BaseDynamicContextProvider
from instructor.dsl.partial import PartialBase


@pytest.fixture
def mock_instructor():
    mock = Mock(spec=instructor.Instructor)
    # Set up the nested mock structure
    mock.chat = Mock()
    mock.chat.completions = Mock()
    mock.chat.completions.create = Mock(return_value=BasicChatOutputSchema(chat_message="Test output"))

    # Make create_partial return an iterable
    mock_response = BasicChatOutputSchema(chat_message="Test output")
    mock_iter = Mock()
    mock_iter.__iter__ = Mock(return_value=iter([mock_response]))
    mock.chat.completions.create_partial.return_value = mock_iter

    return mock


@pytest.fixture
def mock_instructor_async():
    # Changed spec from instructor.Instructor to instructor.client.AsyncInstructor
    mock = Mock(spec=instructor.client.AsyncInstructor)

    # Configure chat.completions structure
    mock.chat = Mock()
    mock.chat.completions = Mock()

    # Make create method awaitable by using an async function
    async def mock_create(*args, **kwargs):
        return BasicChatOutputSchema(chat_message="Test output")

    mock.chat.completions.create = mock_create

    # Mock the create_partial method to return an async generator
    async def mock_create_partial(*args, **kwargs):
        yield BasicChatOutputSchema(chat_message="Test output")

    mock.chat.completions.create_partial = mock_create_partial

    return mock


@pytest.fixture
def mock_history():
    mock = Mock(spec=ChatHistory)
    mock.get_history.return_value = []
    mock.add_message = Mock()
    mock.copy = Mock(return_value=Mock(spec=ChatHistory))
    mock.initialize_turn = Mock()
    return mock


@pytest.fixture
def mock_system_prompt_generator():
    mock = Mock(spec=SystemPromptGenerator)
    mock.generate_prompt.return_value = "Mocked system prompt"
    mock.context_providers = {}
    return mock


@pytest.fixture
def agent_config(mock_instructor, mock_history, mock_system_prompt_generator):
    return AgentConfig(
        client=mock_instructor,
        model="gpt-4o-mini",
        history=mock_history,
        system_prompt_generator=mock_system_prompt_generator,
    )


@pytest.fixture
def agent(agent_config):
    return AtomicAgent[BasicChatInputSchema, BasicChatOutputSchema](agent_config)


@pytest.fixture
def agent_config_async(mock_instructor_async, mock_history, mock_system_prompt_generator):
    return AgentConfig(
        client=mock_instructor_async,
        model="gpt-4o-mini",
        history=mock_history,
        system_prompt_generator=mock_system_prompt_generator,
    )


@pytest.fixture
def agent_async(agent_config_async):
    return AtomicAgent[BasicChatInputSchema, BasicChatOutputSchema](agent_config_async)


def test_initialization(agent, mock_instructor, mock_history, mock_system_prompt_generator):
    assert agent.client == mock_instructor
    assert agent.model == "gpt-4o-mini"
    assert agent.history == mock_history
    assert agent.system_prompt_generator == mock_system_prompt_generator
    assert "max_tokens" not in agent.model_api_parameters


# model_api_parameters should have priority over other settings
def test_initialization_temperature_priority(mock_instructor, mock_history, mock_system_prompt_generator):
    config = AgentConfig(
        client=mock_instructor,
        model="gpt-4o-mini",
        history=mock_history,
        system_prompt_generator=mock_system_prompt_generator,
        model_api_parameters={"temperature": 1.0},
    )
    agent = AtomicAgent[BasicChatInputSchema, BasicChatOutputSchema](config)
    assert agent.model_api_parameters["temperature"] == 1.0


def test_initialization_without_temperature(mock_instructor, mock_history, mock_system_prompt_generator):
    config = AgentConfig(
        client=mock_instructor,
        model="gpt-4o-mini",
        history=mock_history,
        system_prompt_generator=mock_system_prompt_generator,
        model_api_parameters={"temperature": 0.5},
    )
    agent = AtomicAgent[BasicChatInputSchema, BasicChatOutputSchema](config)
    assert agent.model_api_parameters["temperature"] == 0.5


def test_initialization_without_max_tokens(mock_instructor, mock_history, mock_system_prompt_generator):
    config = AgentConfig(
        client=mock_instructor,
        model="gpt-4o-mini",
        history=mock_history,
        system_prompt_generator=mock_system_prompt_generator,
        model_api_parameters={"max_tokens": 1024},
    )
    agent = AtomicAgent[BasicChatInputSchema, BasicChatOutputSchema](config)
    assert agent.model_api_parameters["max_tokens"] == 1024


def test_initialization_system_role_equals_developer(mock_instructor, mock_history, mock_system_prompt_generator):
    config = AgentConfig(
        client=mock_instructor,
        model="gpt-4o-mini",
        history=mock_history,
        system_prompt_generator=mock_system_prompt_generator,
        system_role="developer",
        model_api_parameters={},  # No temperature specified
    )
    agent = AtomicAgent[BasicChatInputSchema, BasicChatOutputSchema](config)
    _ = agent._prepare_messages()
    assert isinstance(agent.messages, list) and agent.messages[0]["role"] == "developer"


def test_initialization_system_role_equals_None(mock_instructor, mock_history, mock_system_prompt_generator):
    config = AgentConfig(
        client=mock_instructor,
        model="gpt-4o-mini",
        history=mock_history,
        system_prompt_generator=mock_system_prompt_generator,
        system_role=None,
        model_api_parameters={},  # No temperature specified
    )
    agent = AtomicAgent[BasicChatInputSchema, BasicChatOutputSchema](config)
    _ = agent._prepare_messages()
    assert isinstance(agent.messages, list) and len(agent.messages) == 0


def test_reset_history(agent, mock_history):
    initial_history = agent.initial_history
    agent.reset_history()
    assert agent.history != initial_history
    mock_history.copy.assert_called_once()


def test_get_context_provider(agent, mock_system_prompt_generator):
    mock_provider = Mock(spec=BaseDynamicContextProvider)
    mock_system_prompt_generator.context_providers = {"test_provider": mock_provider}

    result = agent.get_context_provider("test_provider")
    assert result == mock_provider

    with pytest.raises(KeyError):
        agent.get_context_provider("non_existent_provider")


def test_register_context_provider(agent, mock_system_prompt_generator):
    mock_provider = Mock(spec=BaseDynamicContextProvider)
    agent.register_context_provider("new_provider", mock_provider)

    assert "new_provider" in mock_system_prompt_generator.context_providers
    assert mock_system_prompt_generator.context_providers["new_provider"] == mock_provider


def test_unregister_context_provider(agent, mock_system_prompt_generator):
    mock_provider = Mock(spec=BaseDynamicContextProvider)
    mock_system_prompt_generator.context_providers = {"test_provider": mock_provider}

    agent.unregister_context_provider("test_provider")
    assert "test_provider" not in mock_system_prompt_generator.context_providers

    with pytest.raises(KeyError):
        agent.unregister_context_provider("non_existent_provider")


def test_no_type_parameters(mock_instructor):
    custom_config = AgentConfig(
        client=mock_instructor,
        model="gpt-4o-mini",
    )

    custom_agent = AtomicAgent(custom_config)

    assert custom_agent.input_schema == BasicChatInputSchema
    assert custom_agent.output_schema == BasicChatOutputSchema


def test_custom_input_output_schemas(mock_instructor):
    class CustomInputSchema(BaseModel):
        custom_field: str

    class CustomOutputSchema(BaseModel):
        result: str

    custom_config = AgentConfig(
        client=mock_instructor,
        model="gpt-4o-mini",
    )

    custom_agent = AtomicAgent[CustomInputSchema, CustomOutputSchema](custom_config)

    assert custom_agent.input_schema == CustomInputSchema
    assert custom_agent.output_schema == CustomOutputSchema


def test_base_agent_io_str_and_rich():
    class TestIO(BaseIOSchema):
        """TestIO docstring"""

        field: str

    test_io = TestIO(field="test")
    assert str(test_io) == '{"field":"test"}'
    assert test_io.__rich__() is not None  # Just check if it returns something, as we can't easily compare Rich objects


def test_base_io_schema_empty_docstring():
    with pytest.raises(ValueError, match="must have a non-empty docstring"):

        class EmptyDocStringSchema(BaseIOSchema):
            """"""

            pass


def test_base_io_schema_model_json_schema_no_description():
    class TestSchema(BaseIOSchema):
        """Test schema docstring."""

        field: str

    # Mock the superclass model_json_schema to return a schema without a description
    with patch("pydantic.BaseModel.model_json_schema", return_value={}):
        schema = TestSchema.model_json_schema()

    assert "description" in schema
    assert schema["description"] == "Test schema docstring."


def test_run(agent, mock_history):
    # Use the agent fixture that's already configured correctly
    mock_input = BasicChatInputSchema(chat_message="Test input")

    result = agent.run(mock_input)

    # Assertions
    assert result.chat_message == "Test output"
    assert agent.current_user_input == mock_input

    mock_history.add_message.assert_has_calls([call("user", mock_input), call("assistant", result)])


def test_run_stream(mock_instructor, mock_history):
    # Create a AgentConfig with system_role set to None
    config = AgentConfig(
        client=mock_instructor,
        model="gpt-4o-mini",
        history=mock_history,
        system_prompt_generator=None,  # No system prompt generator
    )
    agent = AtomicAgent[BasicChatInputSchema, BasicChatOutputSchema](config)

    mock_input = BasicChatInputSchema(chat_message="Test input")
    mock_output = BasicChatOutputSchema(chat_message="Test output")

    for result in agent.run_stream(mock_input):
        pass

    assert result == mock_output
    assert agent.current_user_input == mock_input

    mock_history.add_message.assert_has_calls([call("user", mock_input), call("assistant", mock_output)])


@pytest.mark.asyncio
async def test_run_async(agent_async, mock_history):
    # Create a mock input
    mock_input = BasicChatInputSchema(chat_message="Test input")
    mock_output = BasicChatOutputSchema(chat_message="Test output")

    # Get response from run_async method
    response = await agent_async.run_async(mock_input)

    # Assertions
    assert response == mock_output
    assert agent_async.current_user_input == mock_input
    mock_history.add_message.assert_has_calls([call("user", mock_input), call("assistant", mock_output)])


@pytest.mark.asyncio
async def test_run_async_stream(agent_async, mock_history):
    # Create a mock input
    mock_input = BasicChatInputSchema(chat_message="Test input")
    mock_output = BasicChatOutputSchema(chat_message="Test output")

    responses = []
    # Get response from run_async_stream method
    async for response in agent_async.run_async_stream(mock_input):
        responses.append(response)

    # Assertions
    assert len(responses) == 1
    assert responses[0] == mock_output
    assert agent_async.current_user_input == mock_input

    # Verify that both user input and assistant response were added to history
    mock_history.add_message.assert_any_call("user", mock_input)

    # Create the expected full response content to check
    full_response_content = agent_async.output_schema(**responses[0].model_dump())
    mock_history.add_message.assert_any_call("assistant", full_response_content)


def test_model_from_chunks_patched():
    class TestPartialModel(PartialBase):
        @classmethod
        def get_partial_model(cls):
            class PartialModel(BaseModel):
                field: str

            return PartialModel

    chunks = ['{"field": "hel', 'lo"}']
    expected_values = ["hel", "hello"]

    generator = TestPartialModel.model_from_chunks(chunks)
    results = [result.field for result in generator]

    assert results == expected_values


@pytest.mark.asyncio
async def test_model_from_chunks_async_patched():
    class TestPartialModel(PartialBase):
        @classmethod
        def get_partial_model(cls):
            class PartialModel(BaseModel):
                field: str

            return PartialModel

    async def async_gen():
        yield '{"field": "hel'
        yield 'lo"}'

    expected_values = ["hel", "hello"]

    generator = TestPartialModel.model_from_chunks_async(async_gen())
    results = []
    async for result in generator:
        results.append(result.field)

    assert results == expected_values
