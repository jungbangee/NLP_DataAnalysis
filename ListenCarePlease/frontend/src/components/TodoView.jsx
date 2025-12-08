import React, { useState, useEffect } from 'react';
import { Calendar, momentLocalizer } from 'react-big-calendar';
import moment from 'moment';
import 'moment/locale/ko';
import 'react-big-calendar/lib/css/react-big-calendar.css';
import { extractTodos, getTodos, deleteTodo } from '../services/api';

// moment 한국어 설정
moment.locale('ko');
const localizer = momentLocalizer(moment);

const TodoView = ({ fileId }) => {
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [todos, setTodos] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);

  useEffect(() => {
    if (fileId) {
      fetchTodos();
    }
  }, [fileId]);

  const fetchTodos = async () => {
    try {
      setLoading(true);
      const data = await getTodos(fileId);

      const events = data.todos.map(todo => ({
        id: todo.id,
        title: `[${todo.priority}] ${todo.task}`,
        start: new Date(todo.due_date),
        end: new Date(todo.due_date),
        resource: {
          assignee: todo.assignee,
          priority: todo.priority,
          task: todo.task
        }
      }));

      setTodos(events);
    } catch (error) {
      console.error('TODO 조회 실패:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleExtractTodos = async () => {
    if (!confirm('회의록에서 TODO를 추출하시겠습니까? 기존 TODO는 삭제됩니다.')) return;

    try {
      setExtracting(true);
      await extractTodos(fileId);
      alert('TODO 추출 완료!');
      fetchTodos();
    } catch (error) {
      console.error('TODO 추출 실패:', error);
      alert('TODO 추출 실패');
    } finally {
      setExtracting(false);
    }
  };

  const handleDeleteTodo = async (todoId) => {
    if (!confirm('삭제하시겠습니까?')) return;
    try {
      await deleteTodo(fileId, todoId);
      fetchTodos();
      setSelectedEvent(null);
    } catch (error) {
      console.error('삭제 실패:', error);
    }
  };

  const eventStyleGetter = (event) => {
    let backgroundColor = '#10b981';
    if (event.resource.priority === 'High') backgroundColor = '#ef4444';
    else if (event.resource.priority === 'Medium') backgroundColor = '#f59e0b';

    return {
      style: {
        backgroundColor,
        borderRadius: '5px',
        opacity: 0.8,
        color: 'white',
        border: '0px',
        display: 'block',
        fontSize: '0.8rem'
      }
    };
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl border border-bg-accent/30">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-blue"></div>
      </div>
    );
  }

  return (
    <div className="bg-bg-tertiary dark:bg-bg-tertiary-dark rounded-xl shadow-lg border border-bg-accent/30 p-4 h-[600px] flex flex-col">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <span>✅</span> TODO 캘린더
        </h2>
        <button
          onClick={handleExtractTodos}
          disabled={extracting}
          className={`px-3 py-1 text-sm rounded-lg font-medium transition-all ${
            extracting
              ? 'bg-gray-400 cursor-not-allowed text-white'
              : 'bg-accent-sage dark:bg-accent-teal hover:opacity-90 text-gray-900 dark:text-white'
          }`}
        >
          {extracting ? '추출 중...' : '🔄 다시 추출'}
        </button>
      </div>

      <div className="flex-1 bg-white dark:bg-gray-800 rounded-lg p-2 overflow-hidden">
        <Calendar
          localizer={localizer}
          events={todos}
          startAccessor="start"
          endAccessor="end"
          style={{ height: '100%' }}
          eventPropGetter={eventStyleGetter}
          onSelectEvent={setSelectedEvent}
          views={['month', 'agenda']}
          defaultView='month'
          messages={{
            today: '오늘',
            previous: '<',
            next: '>',
            month: '월',
            agenda: '목록',
            noEventsInRange: '일정이 없습니다.',
          }}
        />
      </div>

      {selectedEvent && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={() => setSelectedEvent(null)}>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-sm w-full mx-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-bold mb-2">{selectedEvent.resource.task}</h3>
            <p className="text-sm text-gray-600 mb-1">담당: {selectedEvent.resource.assignee}</p>
            <p className="text-sm text-gray-600 mb-4">마감: {moment(selectedEvent.start).format('YYYY-MM-DD')}</p>
            <div className="flex gap-2">
              <button onClick={() => handleDeleteTodo(selectedEvent.id)} className="flex-1 bg-red-500 text-white py-2 rounded">삭제</button>
              <button onClick={() => setSelectedEvent(null)} className="flex-1 bg-gray-200 text-gray-800 py-2 rounded">닫기</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TodoView;
