import { useDispatch } from 'react-redux';
import { AppDispatch } from 'store';

const useAppDispatch = () => useDispatch<AppDispatch>();

export default useAppDispatch;
