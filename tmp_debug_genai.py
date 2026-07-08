import asyncio
import traceback
import google.generativeai as genai

async def main():
    model = genai.GenerativeModel('gemini-2.5-flash')
    tools = [
        {
            'name': 'test_tool',
            'description': 'test',
            'parameters': {'type': 'object'},
        }
    ]
    try:
        response = await model.generate_content_async(
            contents=[{'role': 'user', 'parts': ['hi']}],
            tools=tools,
            tool_config={'function_calling_config': {'mode': 'auto'}},
            generation_config={'max_output_tokens': 10},
        )
        print('RESPONSE', response)
    except Exception as e:
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
