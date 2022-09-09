import React from 'react';
import ReactDOM from 'react-dom';

export interface Props {
    children: React.ReactNode;
}

const Portal: React.FC<Props> = ({ children }) => {
    return ReactDOM.createPortal(children, document.body);
};

export default Portal;
